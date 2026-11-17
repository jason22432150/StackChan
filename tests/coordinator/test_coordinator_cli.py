"""P2-04 smoke test for the installed Coordinator entry point."""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import sys
from pathlib import Path

import pytest
import trustme
from websockets.asyncio.client import connect

from stackchan import main as stackchan_main
from stackchan.security.identity import TokenHasher
from stackchan.security.policy import PolicyService
from stackchan.security.store import SecurityStore


def _arguments(db: Path, cert: Path, key: Path) -> list[str]:
    return [
        "coordinator", "serve-device", "--security-db", str(db), "--cert", str(cert), "--key", str(key),
        "--port", "0", "--generation", "17",
    ]


def test_coordinator_cli_requires_pepper_before_opening_files(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("STACKCHAN_SECURITY_PEPPER", raising=False)
    missing_database = tmp_path / "missing.sqlite"
    with pytest.raises(SystemExit) as error:
        stackchan_main(_arguments(missing_database, tmp_path / "cert.pem", tmp_path / "key.pem"))
    assert error.value.code == 2
    assert "STACKCHAN_SECURITY_PEPPER" in capsys.readouterr().err
    assert not missing_database.exists()


def test_coordinator_cli_serves_policy_and_stream(tmp_path: Path) -> None:
    pepper = "bench-test-pepper"
    token = "bench-device-token"
    db = tmp_path / "security # bench.sqlite"
    with SecurityStore(db, hasher=TokenHasher(pepper.encode())) as store:
        store.upsert_subject("device-a", "device", "CoreS3")
        store.issue_grant(
            grant_id="grant", subject_id="device-a", subject_type="device", token_plaintext=token,
            scopes=["device:policy", "device:stream"], expires_at="2099-01-01T00:00:00Z",
        )
        policies = PolicyService(store)
        policies.publish({
            "policy_id": "desk", "version": "v1", "privacy_mode": "private",
            "valid_until": "2099-01-01T00:00:00Z",
        })
        policies.bind_device("device-a", "desk", "v1")
    before = db.read_bytes()

    ca = trustme.CA()
    identity = ca.issue_cert("127.0.0.1")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    identity.cert_chain_pems[0].write_to_path(cert)
    identity.private_key_pem.write_to_path(key)
    client_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ca.configure_trust(client_tls)

    async def exercise() -> None:
        child = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "from stackchan import main; main()", *_arguments(db, cert, key),
            env={**os.environ, "STACKCHAN_SECURITY_PEPPER": pepper},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            async with asyncio.timeout(5):
                assert child.stdout is not None
                ready = (await child.stdout.readline()).decode()
                assert ready.startswith("Coordinator ready on 127.0.0.1:")
                assert pepper not in ready and token not in ready
                port = int(ready.split("127.0.0.1:", 1)[1].split(" ", 1)[0])
                reader, writer = await asyncio.open_connection("127.0.0.1", port, ssl=client_tls)
                try:
                    writer.write((
                        "GET /v1/devices/device-a/policy HTTP/1.1\r\n"
                        "Host: 127.0.0.1\r\n"
                        f"Authorization: Bearer {token}\r\n"
                        "Connection: close\r\n\r\n"
                    ).encode())
                    await writer.drain()
                    response = await reader.read()
                finally:
                    writer.close()
                    await writer.wait_closed()
                head, _, body = response.partition(b"\r\n\r\n")
                assert head.startswith(b"HTTP/1.1 200 ")
                policy = json.loads(body)
                async with connect(
                    f"wss://127.0.0.1:{port}/v1/device-stream",
                    ssl=client_tls,
                    proxy=None,
                    additional_headers={
                        "Authorization": f"Bearer {token}",
                        "X-StackChan-Device-Id": "device-a",
                        "X-StackChan-Policy-Version": policy["version"],
                    },
                ) as websocket:
                    heartbeat = json.loads(await websocket.recv())
                    assert heartbeat["type"] == "heartbeat" and heartbeat["generation"] == 17
                    assert heartbeat["device_id"] == "device-a" and heartbeat["policy_version"] == "v1"
        finally:
            if child.returncode is None:
                child.terminate()
            await child.communicate()

    asyncio.run(exercise())
    assert db.read_bytes() == before
