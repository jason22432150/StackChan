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
from stackchan.coordinator import pairing_server
from stackchan.contracts.authz import ApiGate
from stackchan.security.auth_bridge import StoreBackedTokenDirectory
from stackchan.security.identity import TokenHasher
from stackchan.security.pairing import PairingService
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


@pytest.fixture
def split_pairing(bench, monkeypatch):
    """Exercise real TLS on loopback; substitute only LAN bind/peer metadata."""
    original = asyncio.start_server
    device_peer = ["192.168.1.20"]
    calls = []

    class PeerWriter:
        def __init__(self, writer, peer):
            self.writer, self.peer = writer, peer

        def get_extra_info(self, name):
            if name == "peername":
                return None if self.peer[0] is None else (self.peer[0], 50000)
            return self.writer.get_extra_info(name)

        def __getattr__(self, name):
            return getattr(self.writer, name)

    async def local_bind(handler, *, host, **kwargs):
        calls.append((host, kwargs.copy()))
        if host == "192.168.1.10":
            async def forwarded(reader, writer):
                await handler(reader, PeerWriter(writer, device_peer))
            return await original(forwarded, host="127.0.0.1", **kwargs)
        assert host == "127.0.0.1"
        return await original(handler, host=host, **kwargs)

    monkeypatch.setattr(pairing_server.asyncio, "start_server", local_bind)

    @asynccontextmanager
    async def launch():
        db, _, client = bench
        authority = trustme.CA()
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        authority.issue_cert("127.0.0.1").configure_cert(tls)
        authority.configure_trust(client)
        with SecurityStore(db, hasher=TokenHasher(PEPPER.encode()), existing_only=True) as store:
            async with pairing_server.serve_lan_device_pairing(
                PairingService(store), ApiGate(StoreBackedTokenDirectory(store)), tls,
                host="192.168.1.10", device_ip="192.168.1.20", port=0, admin_port=0,
                device_policy=("desk", "v1"),
            ) as servers:
                yield tuple(server.sockets[0].getsockname()[1] for server in servers)

    return launch, device_peer, calls


def test_split_pairing_device_cannot_confirm_and_admin_cannot_claim(bench, split_pairing):
    _, _, tls = bench
    launch, _, calls = split_pairing

    async def exercise():
        async with launch() as (device, admin):
            challenge, claim = await _start(tls, device)
            path = f"{START}/{challenge['pairing_id']}/complete"
            assert (await _confirm(tls, device, challenge))[0] == 403  # Even with a valid admin token.
            assert (await _post(tls, admin, START, {}))[0] == 403
            assert (await _post(tls, admin, path, **{CLAIM: claim}))[0] == 403
            assert (await _confirm(tls, admin, challenge, token="untrusted"))[0] == 401
            assert (await _post(tls, device, path, **{CLAIM: claim}))[0] == 403
            assert (await _confirm(tls, admin, challenge))[0] == 200
            status, _, grant = await _post(tls, device, path, **{CLAIM: claim})
            assert status == 200 and grant["subject_type"] == "device"
            assert (await _post(tls, device, path, **{CLAIM: claim}))[0] == 401
        assert [host for host, _ in calls] == ["192.168.1.10", "127.0.0.1"]
        assert all(options["start_serving"] is False for _, options in calls)

    asyncio.run(exercise())


def test_split_pairing_peer_filter_cannot_be_bypassed_with_forwarded_headers(bench, split_pairing):
    db, _, tls = bench
    launch, peer, _ = split_pairing

    async def exercise():
        async with launch() as (device, admin):
            challenge, claim = await _start(tls, device)
            assert (await _confirm(tls, admin, challenge))[0] == 200
            for source in ("192.168.1.21", None):
                peer[0] = source
                for path in (START, f"{START}/{challenge['pairing_id']}/confirm", f"{START}/{challenge['pairing_id']}/complete"):
                    status, _, result = await _post(tls, device, path, **{
                        CLAIM: claim, "Authorization": f"Bearer {ADMIN}", "X-Forwarded-For": "192.168.1.20",
                    })
                    assert status == 403 and "access_token" not in result
            peer[0] = "192.168.1.20"
            assert (await _post(tls, device, f"{START}/{challenge['pairing_id']}/complete", **{CLAIM: claim}))[0] == 200

    asyncio.run(exercise())
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT count(*) FROM pairing_sessions").fetchone()[0] == 1


def test_split_pairing_denial_and_restart_clear_shared_claims(bench, split_pairing):
    _, _, tls = bench
    launch, _, _ = split_pairing

    async def exercise():
        async with launch() as (device, admin):
            denied, claim = await _start(tls, device)
            assert (await _confirm(tls, admin, denied, approved=False))[0] == 200
            assert (await _post(tls, device, f"{START}/{denied['pairing_id']}/complete", **{CLAIM: claim}))[0] == 401
            old, old_claim = await _start(tls, device)
            assert (await _confirm(tls, admin, old))[0] == 200
        async with launch() as (device, admin):
            assert (await _post(tls, device, f"{START}/{old['pairing_id']}/complete", **{CLAIM: old_claim}))[0] == 401
            fresh, claim = await _start(tls, device)
            assert (await _confirm(tls, admin, fresh))[0] == 200
            assert (await _post(tls, device, f"{START}/{fresh['pairing_id']}/complete", **{CLAIM: claim}))[0] == 200

    asyncio.run(exercise())


@pytest.mark.parametrize(("host", "device", "admin"), [
    ("0.0.0.0", "192.168.1.20", 9444), ("8.8.8.8", "192.168.1.20", 9444),
    ("localhost", "192.168.1.20", 9444), ("::", "192.168.1.20", 9444),
    ("192.168.1.10", None, 9444), ("192.168.1.10", "192.168.1.20", None),
    ("192.168.1.10", "8.8.8.8", 9444), ("192.168.1.10", "192.168.1.10", 9444),
    ("192.168.1.10", "192.168.1.20", -1), ("192.168.1.10", "192.168.1.20", 65536),
    ("127.0.0.1", None, 9444),
])
def test_pairing_cli_rejects_unsafe_split_configuration(bench, host, device, admin):
    db, args, _ = bench
    before = db.read_bytes()
    args += ["--listen", host]
    if device is not None:
        args += ["--device-ip", device]
    if admin is not None:
        args += ["--admin-port", str(admin)]
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2
    assert db.read_bytes() == before


@pytest.mark.parametrize("failure", ["admin_bind", "device_start", "admin_start", "cancel"])
def test_split_pairing_closes_all_listeners_on_failure_or_cancellation(monkeypatch, failure):
    events = []

    class Server:
        def __init__(self, role):
            self.role = role

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            events.append((self.role, "closed"))

        async def start_serving(self):
            events.append((self.role, "start"))
            if failure == f"{self.role}_start":
                raise OSError("start failed")

    async def listener(*args, role, **kwargs):
        assert kwargs["start_serving"] is False
        events.append((role, "bind"))
        if failure == "admin_bind" and role == "admin":
            raise OSError("bind failed")
        return Server(role)

    monkeypatch.setattr(pairing_server, "_pairing_listener", listener)

    async def exercise():
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        with pytest.raises(asyncio.CancelledError if failure == "cancel" else OSError):
            async with pairing_server.serve_lan_device_pairing(
                object(), object(), tls, host="192.168.1.10", device_ip="192.168.1.20",
                port=9443, admin_port=9444, device_policy=("desk", "v1"),
            ):
                raise asyncio.CancelledError
        assert events[:2] == [("device", "bind"), ("admin", "bind")]
        assert ("device", "closed") in events
        if failure != "admin_bind":
            assert ("admin", "closed") in events
        else:
            assert not any(event == "start" for _, event in events)

    asyncio.run(exercise())


def test_pairing_cli_passes_explicit_split_configuration(bench, monkeypatch):
    _, args, _ = bench
    captured = []

    async def serve(*values):
        captured.append(values)

    monkeypatch.setattr(cli, "_serve_pairing", serve)
    assert cli.main(args + ["--listen", "192.168.1.10", "--device-ip", "192.168.1.20", "--admin-port", "9444"]) == 0
    assert captured[0][3:] == (0, "desk", "v1", "192.168.1.10", "192.168.1.20", 9444)


def test_pairing_cli_split_runtime_serves_both_ports_and_closes_on_cancel(bench, split_pairing, monkeypatch):
    db, args, client = bench
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(args[args.index("--cert") + 1], args[args.index("--key") + 1])

    async def exercise():
        ready = asyncio.Queue()
        monkeypatch.setattr(cli, "print", lambda line, **kwargs: ready.put_nowait(line), raising=False)
        task = asyncio.create_task(cli._serve_pairing(
            db, PEPPER.encode(), tls, 0, "desk", "v1", "192.168.1.10", "192.168.1.20", 0,
        ))
        try:
            async with asyncio.timeout(5):
                device_line, admin_line = await ready.get(), await ready.get()
                assert device_line.startswith("Pairing ready on 127.0.0.1:")  # LAN bind is substituted.
                assert admin_line.startswith("Pairing admin ready on 127.0.0.1:")
                ports = [int(line.split("127.0.0.1:")[1].split(" ")[0]) for line in (device_line, admin_line)]
                challenge, claim = await _start(client, ports[0])
                assert (await _confirm(client, ports[1], challenge))[0] == 200
                assert (await _post(client, ports[0], f"{START}/{challenge['pairing_id']}/complete", **{CLAIM: claim}))[0] == 200
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        for port in ports:
            with pytest.raises(OSError):
                await asyncio.open_connection("127.0.0.1", port)

    asyncio.run(exercise())
