from __future__ import annotations

import asyncio
import json
import ssl
from datetime import datetime, timedelta, timezone

import pytest
import trustme

from stackchan.contracts.authz import ApiGate
from stackchan.coordinator.pairing_server import serve_device_pairing
from stackchan.security.auth_bridge import StoreBackedTokenDirectory
from stackchan.security.identity import TokenHasher
from stackchan.security.pairing import PairingService
from stackchan.security.store import SecurityStore

_START = "/v1/pairing/sessions"
_CLAIM = "X-StackChan-Pairing-Claim"
_DEVICE = {"schema_version": "0.1", "subject_type": "device", "display_name": "CoreS3"}


@pytest.fixture
def pairing_transport(tmp_path):
    authority = trustme.CA()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    authority.issue_cert("127.0.0.1").configure_cert(tls)
    client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    authority.configure_trust(client)
    with SecurityStore(tmp_path / "security.sqlite", hasher=TokenHasher(pepper=b"loopback-only")) as store:
        store.upsert_subject("administrator", "admin", "Test administrator")
        store.issue_grant(
            grant_id="admin-grant", subject_id="administrator", subject_type="admin",
            token_plaintext="test-admin-token", scopes=["admin:pairing"], expires_at="2099-01-01T00:00:00Z",
        )
        directory = StoreBackedTokenDirectory(store)
        yield PairingService(store), ApiGate(directory), tls, client, directory


async def _post(client, port, path, payload=None, **headers):
    body = b"" if payload is None else json.dumps(payload).encode()
    request = (
        f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        + "".join(f"{name}: {value}\r\n" for name, value in headers.items())
        + "\r\n"
    ).encode("ascii") + body
    async with asyncio.timeout(5):
        reader, writer = await asyncio.open_connection("127.0.0.1", port, ssl=client)
        try:
            writer.write(request)
            await writer.drain()
            response = await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()
    header, delimiter, content = response.partition(b"\r\n\r\n")
    assert delimiter
    status, *fields = header.decode("ascii").split("\r\n")
    metadata = {name.lower(): value.strip() for name, value in (field.split(":", 1) for field in fields)}
    assert metadata["cache-control"] == "no-store"
    assert int(metadata["content-length"]) == len(content)
    return int(status.split()[1]), metadata, json.loads(content)


async def _start(client, port):
    status, headers, challenge = await _post(client, port, _START, _DEVICE)
    assert status == 200
    assert set(challenge) == {"schema_version", "pairing_id", "subject_type", "user_code", "expires_at"}
    claim = headers[_CLAIM.lower()]
    assert len(claim) >= 32 and claim not in challenge.values()
    return challenge, claim


def _confirm(challenge, approved=True):
    return {
        "schema_version": "0.1", "pairing_id": challenge["pairing_id"],
        "user_code": challenge["user_code"], "approved": approved,
    }


def test_approved_pairing_delivers_token_only_to_claim_holder(pairing_transport):
    service, gate, tls, client, directory = pairing_transport

    async def exercise():
        async with await serve_device_pairing(service, gate, tls, port=0) as server:
            address, port = server.sockets[0].getsockname()
            assert address == "127.0.0.1"
            challenge, claim = await _start(client, port)
            other, other_claim = await _start(client, port)
            session = f"{_START}/{challenge['pairing_id']}"
            complete = f"{session}/complete"
            confirm = f"{session}/confirm"
            assert (await _post(client, port, complete, **{_CLAIM: claim}))[0] == 403
            assert (await _post(client, port, confirm, _confirm(challenge)))[0] == 401
            admin = {"Authorization": "Bearer test-admin-token"}
            assert (await _post(client, port, confirm, _confirm(other), **admin))[0] == 400
            assert (await _post(client, port, confirm, _confirm(challenge), **admin))[0] == 200
            for invalid in ({}, {_CLAIM: other_claim}, {_CLAIM: challenge["user_code"]}):
                status, _, denied = await _post(client, port, complete, **invalid)
                assert status == 401 and "access_token" not in denied

            responses = await asyncio.gather(*(
                _post(client, port, complete, **{_CLAIM: claim}) for _ in range(2)
            ))
            assert sorted(status for status, _, _ in responses) == [200, 401]
            _, headers, grant = next(response for response in responses if response[0] == 200)
            assert grant["pairing_id"] == challenge["pairing_id"]
            assert _CLAIM.lower() not in headers
            principal = directory.resolve(grant["access_token"])
            assert principal is not None
            assert principal.subject_id == grant["subject_id"]
            assert principal.scopes == {"device:policy", "device:receipt", "device:stream"}

    asyncio.run(exercise())


def test_denial_restart_and_untrusted_tls_do_not_deliver_a_grant(pairing_transport):
    service, gate, tls, client, _ = pairing_transport

    async def exercise():
        admin = {"Authorization": "Bearer test-admin-token"}
        async with await serve_device_pairing(service, gate, tls, port=0) as server:
            port = server.sockets[0].getsockname()[1]
            with pytest.raises(ssl.SSLCertVerificationError):
                await _post(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT), port, _START, _DEVICE)
            rejected, rejected_claim = await _start(client, port)
            rejected_path = f"{_START}/{rejected['pairing_id']}"
            assert (await _post(client, port, f"{rejected_path}/confirm", _confirm(rejected, False), **admin))[0] == 200
            assert (await _post(client, port, f"{rejected_path}/complete", **{_CLAIM: rejected_claim}))[0] == 401
            old, old_claim = await _start(client, port)
            old_path = f"{_START}/{old['pairing_id']}"
            assert (await _post(client, port, f"{old_path}/confirm", _confirm(old), **admin))[0] == 200

        async with await serve_device_pairing(service, gate, tls, port=0) as server:
            port = server.sockets[0].getsockname()[1]
            assert (await _post(client, port, f"{old_path}/complete", **{_CLAIM: old_claim}))[0] == 401
            new, new_claim = await _start(client, port)
            new_path = f"{_START}/{new['pairing_id']}"
            assert (await _post(client, port, f"{new_path}/confirm", _confirm(new), **admin))[0] == 200
            status, _, result = await _post(client, port, f"{new_path}/complete", **{_CLAIM: new_claim})
            assert status == 200 and result["pairing_id"] == new["pairing_id"]

    asyncio.run(exercise())


def test_expired_pairing_claim_is_refused(pairing_transport, monkeypatch):
    service, gate, tls, client, _ = pairing_transport
    past = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=11)

    async def exercise():
        async with await serve_device_pairing(service, gate, tls, port=0) as server:
            port = server.sockets[0].getsockname()[1]
            with monkeypatch.context() as clock:
                clock.setattr("stackchan.security.pairing._utc_now", lambda: past)
                challenge, claim = await _start(client, port)

            path = f"{_START}/{challenge['pairing_id']}"
            status, _, result = await _post(client, port, f"{path}/complete", **{_CLAIM: claim})
            assert status == 401 and "access_token" not in result
            status, _, _ = await _post(
                client, port, f"{path}/confirm", _confirm(challenge), Authorization="Bearer test-admin-token",
            )
            assert status == 403

    asyncio.run(exercise())
