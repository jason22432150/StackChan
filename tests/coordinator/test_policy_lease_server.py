"""P2-04 loopback TLS GET /v1/devices/{id}/policy 驗收。"""

from __future__ import annotations

import asyncio
import json
import ssl

import pytest
import trustme

from stackchan.contracts.authz import ApiGate
from stackchan.coordinator.policy_lease import DevicePolicyLeaseService
from stackchan.coordinator.policy_lease_server import serve_device_policy
from stackchan.security.auth_bridge import StoreBackedTokenDirectory
from stackchan.security.identity import TokenHasher
from stackchan.security.policy import PolicyService
from stackchan.security.store import SecurityStore


@pytest.fixture
def policy_tls(tmp_path):
    authority = trustme.CA()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    authority.issue_cert("127.0.0.1").configure_cert(tls)
    client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    authority.configure_trust(client)
    with SecurityStore(tmp_path / "auth.sqlite", hasher=TokenHasher(pepper=b"policy-tls")) as store:
        store.upsert_subject("device-a", "device", "Test device")
        store.upsert_subject("device-b", "device", "Other device")
        for token, subject, scopes in (
            ("valid", "device-a", ["device:policy", "device:stream"]),
            ("stream-only", "device-a", ["device:stream"]),
            ("other", "device-b", ["device:policy"]),
        ):
            store.issue_grant(
                grant_id=token,
                subject_id=subject,
                subject_type="device",
                token_plaintext=token,
                scopes=scopes,
                expires_at="2099-01-01T00:00:00Z",
            )
        policies = PolicyService(store)
        policies.publish(
            {
                "policy_id": "policy",
                "version": "v1",
                "privacy_mode": "private",
                "valid_until": "2099-01-01T00:00:00Z",
            }
        )
        policies.bind_device("device-a", "policy", "v1")
        gate = ApiGate(StoreBackedTokenDirectory(store))
        leases = DevicePolicyLeaseService(gate, policies)
        yield leases, tls, client, policies


async def _http_get(ssl_context: ssl.SSLContext, port: int, path: str, token: str | None) -> tuple[int, dict]:
    reader, writer = await asyncio.open_connection(
        "127.0.0.1", port, ssl=ssl_context, server_hostname="127.0.0.1",
    )
    auth = f"Authorization: Bearer {token}\r\n" if token else ""
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: 127.0.0.1\r\n"
        f"{auth}"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    writer.write(request)
    await writer.drain()
    raw = await reader.read()
    writer.close()
    await writer.wait_closed()
    header, _, body = raw.partition(b"\r\n\r\n")
    status_line = header.split(b"\r\n", 1)[0].decode("ascii")
    status = int(status_line.split()[1])
    payload = json.loads(body.decode("utf-8")) if body else {}
    return status, payload


def test_loopback_tls_policy_requires_trust_and_device_scope(policy_tls) -> None:
    leases, tls, client, _ = policy_tls

    async def exercise() -> None:
        async with await serve_device_policy(leases, tls, port=0) as server:
            port = server.sockets[0].getsockname()[1]
            path = "/v1/devices/device-a/policy"
            with pytest.raises(ssl.SSLCertVerificationError):
                await _http_get(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT), port, path, "valid")
            status, body = await _http_get(client, port, path, None)
            assert status == 401
            assert body["error"] == "unauthorized"
            status, body = await _http_get(client, port, path, "stream-only")
            assert status == 403
            assert body["error"] == "forbidden"
            status, body = await _http_get(client, port, path, "other")
            assert status == 403
            status, body = await _http_get(client, port, "/wrong", "valid")
            assert status == 404
            assert body["error"] == "not_found"

    asyncio.run(exercise())


def test_loopback_tls_policy_returns_openapi_snapshot(policy_tls) -> None:
    leases, tls, client, _ = policy_tls

    async def exercise() -> None:
        async with await serve_device_policy(leases, tls, port=0) as server:
            port = server.sockets[0].getsockname()[1]
            status, body = await _http_get(client, port, "/v1/devices/device-a/policy", "valid")
            assert status == 200
            assert body == {
                "policy_id": "policy",
                "version": "v1",
                "privacy_mode": "private",
                "valid_until": "2099-01-01T00:00:00Z",
            }
            assert "revoked" not in body
            assert "expires_utc_ms" not in body

    asyncio.run(exercise())


def test_loopback_tls_policy_revocation_fails_closed(policy_tls) -> None:
    leases, tls, client, policies = policy_tls

    async def exercise() -> None:
        async with await serve_device_policy(leases, tls, port=0) as server:
            port = server.sockets[0].getsockname()[1]
            policies.revoke("policy", "v1")
            status, body = await _http_get(client, port, "/v1/devices/device-a/policy", "valid")
            assert status == 403
            assert body["error"] == "forbidden"
            assert "policy_revoked" in body["message"]

    asyncio.run(exercise())
