"""Real loopback TLS tests of the pairing CLI and its writable-store boundary."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import ssl
import sys
from contextlib import asynccontextmanager

import pytest
import trustme

from stackchan.coordinator import cli
from stackchan.security.identity import TokenHasher
from stackchan.security.policy import PolicyService
from stackchan.security.store import SecurityStore

PEPPER = "pairing-cli-test-pepper"
ADMIN = "pairing-cli-test-admin"
CLAIM = "X-StackChan-Pairing-Claim"
START = "/v1/pairing/sessions"


@pytest.fixture
def bench(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKCHAN_SECURITY_PEPPER", PEPPER)
    db = tmp_path / "security # pairing.sqlite"
    with SecurityStore(db, hasher=TokenHasher(PEPPER.encode())) as store:
        store.upsert_subject("admin", "admin", "Operator")
        store.issue_grant(
            grant_id="admin-grant", subject_id="admin", subject_type="admin", token_plaintext=ADMIN,
            scopes=["admin:pairing"], expires_at="2099-01-01T00:00:00Z",
        )
        PolicyService(store).publish({
            "policy_id": "desk", "version": "v1", "privacy_mode": "private",
            "valid_until": "2099-01-01T00:00:00Z",
        })
    ca = trustme.CA()
    identity = ca.issue_cert("127.0.0.1")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    identity.cert_chain_pems[0].write_to_path(cert)
    identity.private_key_pem.write_to_path(key)
    client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ca.configure_trust(client)
    args = [
        "serve-pairing", "--security-db", str(db), "--cert", str(cert), "--key", str(key),
        "--port", "0", "--policy-id", "desk", "--policy-version", "v1",
    ]
    return db, args, client


@asynccontextmanager
async def _launch(args):
    child = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "from stackchan import main; main()", "coordinator", *args,
        env=os.environ.copy(), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(10):
            ready = (await child.stdout.readline()).decode()
        assert ready.startswith("Pairing ready on 127.0.0.1:")
        assert PEPPER not in ready and ADMIN not in ready
        yield int(ready.split("127.0.0.1:")[1].split(" ")[0])
    finally:
        if child.returncode is None:
            child.terminate()
        _, errors = await child.communicate()
        assert not errors, errors.decode()


async def _post(tls, port, path, payload=None, **headers):
    body = b"" if payload is None else json.dumps(payload).encode()
    request = (
        f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        + "".join(f"{key}: {value}\r\n" for key, value in headers.items()) + "\r\n"
    ).encode() + body
    async with asyncio.timeout(5):
        reader, writer = await asyncio.open_connection("127.0.0.1", port, ssl=tls)
        try:
            writer.write(request)
            await writer.drain()
            response = await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()
    head, _, content = response.partition(b"\r\n\r\n")
    line, *fields = head.decode().split("\r\n")
    metadata = dict(field.split(": ", 1) for field in fields)
    return int(line.split()[1]), metadata, json.loads(content)


async def _start(tls, port):
    status, headers, challenge = await _post(tls, port, START, {
        "schema_version": "0.1", "subject_type": "device", "display_name": "CoreS3",
    })
    assert status == 200
    return challenge, headers[CLAIM]


async def _confirm(tls, port, challenge, approved=True, token=ADMIN):
    return await _post(tls, port, f"{START}/{challenge['pairing_id']}/confirm", {
        "schema_version": "0.1", "pairing_id": challenge["pairing_id"],
        "user_code": challenge["user_code"], "approved": approved,
    }, Authorization=f"Bearer {token}")


def test_cli_pairing_approval_denial_and_process_restart(bench):
    db, args, tls = bench

    async def exercise():
        async with _launch(args) as port:
            denied, claim = await _start(tls, port)
            assert (await _confirm(tls, port, denied, token="untrusted"))[0] == 401
            assert (await _confirm(tls, port, denied, approved=False))[0] == 200
            assert (await _post(tls, port, f"{START}/{denied['pairing_id']}/complete", **{CLAIM: claim}))[0] == 401
            challenge, claim = await _start(tls, port)
            path = f"{START}/{challenge['pairing_id']}/complete"
            assert (await _post(tls, port, path, **{CLAIM: claim}))[0] == 403
            assert (await _confirm(tls, port, challenge))[0] == 200
            status, _, grant = await _post(tls, port, path, **{CLAIM: claim})
            assert status == 200
            assert (await _post(tls, port, path, **{CLAIM: claim}))[0] == 401
            old, old_claim = await _start(tls, port)
            assert (await _confirm(tls, port, old))[0] == 200
        async with _launch(args) as port:
            assert (await _post(tls, port, f"{START}/{old['pairing_id']}/complete", **{CLAIM: old_claim}))[0] == 401
            fresh, fresh_claim = await _start(tls, port)
            assert (await _confirm(tls, port, fresh))[0] == 200
            status, _, new_grant = await _post(
                tls, port, f"{START}/{fresh['pairing_id']}/complete", **{CLAIM: fresh_claim},
            )
            assert status == 200 and new_grant["access_token"] != grant["access_token"]
        return grant, new_grant

    grants = asyncio.run(exercise())
    with SecurityStore(db, hasher=TokenHasher(PEPPER.encode()), read_only=True) as store:
        for grant in grants:
            assert store.get_device_binding(grant["subject_id"])["policy_version"] == "v1"
            assert grant["access_token"].encode() not in db.read_bytes()


@pytest.mark.parametrize("extra", [
    ["--listen", "0.0.0.0"], ["--device-ip", "192.168.1.20"],
    ["--port", "-1"], ["--port", "65536"], ["--policy-id", " "], ["--policy-version", ""],
])
def test_cli_refuses_unsupported_or_invalid_pairing_options(bench, extra):
    db, args, _ = bench
    before = db.read_bytes()
    with pytest.raises(SystemExit) as error:
        cli.main([*args, *extra])
    assert error.value.code == 2
    assert db.read_bytes() == before


@pytest.mark.parametrize("missing_option", ["--policy-id", "--policy-version"])
def test_cli_requires_explicit_pairing_policy(bench, missing_option):
    _, args, _ = bench
    index = args.index(missing_option)
    with pytest.raises(SystemExit) as error:
        cli.main(args[:index] + args[index + 2:])
    assert error.value.code == 2


@pytest.mark.parametrize("kind", ["missing", "empty"])
def test_cli_does_not_create_or_initialize_a_security_database(bench, tmp_path, kind, capsys):
    _, args, _ = bench
    path = tmp_path / "uninitialized.sqlite"
    if kind == "empty":
        with sqlite3.connect(path):
            pass
    index = args.index("--security-db") + 1
    args[index] = str(path)
    assert cli.main(args) == 1
    assert "existing security database" in capsys.readouterr().err
    if kind == "missing":
        assert not path.exists()
    else:
        assert path.read_bytes() == b""


def test_pairing_cli_requires_pepper_before_opening_files(bench, monkeypatch):
    db, args, _ = bench
    before = db.read_bytes()
    monkeypatch.delenv("STACKCHAN_SECURITY_PEPPER")
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2
    assert db.read_bytes() == before


@pytest.mark.parametrize("policy_state", ["missing", "revoked", "expired"])
def test_cli_refuses_grants_for_unusable_selected_policy(bench, policy_state):
    db, args, tls = bench
    with SecurityStore(db, hasher=TokenHasher(PEPPER.encode())) as store:
        if policy_state == "missing":
            args[args.index("--policy-id") + 1] = "unknown"
        elif policy_state == "revoked":
            PolicyService(store).revoke("desk", "v1")
        else:
            PolicyService(store).publish({
                "policy_id": "desk", "version": "expired", "privacy_mode": "private",
                "valid_until": "2000-01-01T00:00:00Z",
            })
            args[args.index("--policy-version") + 1] = "expired"

    async def exercise():
        async with _launch(args) as port:
            challenge, claim = await _start(tls, port)
            assert (await _confirm(tls, port, challenge))[0] == 200
            status, _, response = await _post(
                tls, port, f"{START}/{challenge['pairing_id']}/complete", **{CLAIM: claim},
            )
            assert status == 403 and "access_token" not in response
        return challenge["pairing_id"]

    pairing_id = asyncio.run(exercise())
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT count(*) FROM subjects").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM authorization_grants").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM device_policy_bindings").fetchone()[0] == 0
        assert connection.execute(
            "SELECT status FROM pairing_sessions WHERE pairing_id=?", (pairing_id,),
        ).fetchone()[0] == "approved"


@pytest.mark.parametrize("failure", ["certificate", "listener"])
def test_pairing_startup_failure_is_sanitized(bench, monkeypatch, capsys, failure):
    db, args, _ = bench
    before = db.read_bytes()
    if failure == "certificate":
        args[args.index("--cert") + 1] = str(db.parent / "missing-certificate.pem")
    else:
        async def refused(*args):
            raise OSError(f"sensitive details: {PEPPER}")

        monkeypatch.setattr(cli, "_serve_pairing", refused)
    assert cli.main(args) == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err and "ready" not in captured.out
    assert PEPPER not in captured.err and ADMIN not in captured.err
    assert db.read_bytes() == before
