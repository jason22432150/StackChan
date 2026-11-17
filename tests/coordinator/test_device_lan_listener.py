"""P2-04 LAN configuration tests without binding a LAN interface."""

from __future__ import annotations

import ssl
from http import HTTPStatus
from types import SimpleNamespace

import pytest
import trustme
from websockets.datastructures import Headers
from websockets.http11 import Request

from stackchan.coordinator import cli, device_stream_server


@pytest.mark.parametrize(
    ("host", "device_ip"),
    [
        ("0.0.0.0", "192.168.1.15"),
        ("8.8.8.8", "192.168.1.15"),
        ("100.64.1.2", "192.168.1.15"),
        ("localhost", "192.168.1.15"),
        ("::", "192.168.1.15"),
        ("192.168.1.10", None),
        ("192.168.1.10", "8.8.8.8"),
        ("192.168.1.10", "192.168.1.10"),
        ("127.0.0.1", "192.168.1.15"),
    ],
)
def test_listener_rejects_uncontrolled_bind(host, device_ip) -> None:
    with pytest.raises(ValueError):
        device_stream_server.validate_device_listener(host, device_ip)


def test_lan_peer_filter_applies_before_policy_and_stream_auth(monkeypatch) -> None:
    allowed_ip = "192.168.1.15"
    auth_calls = []

    def policy_response(*args, **kwargs):
        auth_calls.append("policy")
        return HTTPStatus.UNAUTHORIZED, b"{}"

    def stream_credentials(headers):
        auth_calls.append("stream")
        return None

    def capture_listener(handler, host, port, *, process_request, **kwargs):
        assert (host, port) == ("192.168.1.10", 8443)
        assert kwargs["ssl"] is tls
        return process_request

    monkeypatch.setattr(device_stream_server, "serve", capture_listener)
    monkeypatch.setattr(device_stream_server, "build_device_policy_response", policy_response)
    monkeypatch.setattr(device_stream_server, "_device_credentials", stream_credentials)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    process = device_stream_server.serve_device_stream(
        object(), tls, port=8443, generation=1, heartbeat_interval=1, pong_timeout=2,
        policy_leases=object(), host="192.168.1.10", device_ip=allowed_ip,
    )
    for path in ("/v1/devices/device-a/policy", "/v1/device-stream"):
        request = Request(path, Headers([("X-Forwarded-For", allowed_ip)]))
        for peer in (None, ("192.168.1.16", 50000)):
            socket = SimpleNamespace(remote_address=peer, respond=lambda status, text: status)
            assert process(socket, request) == HTTPStatus.FORBIDDEN
    assert auth_calls == []

    socket = SimpleNamespace(remote_address=(allowed_ip, 50000), respond=lambda status, text: status)
    assert process(socket, Request("/v1/devices/device-a/policy", Headers())).status_code == 401
    assert process(socket, Request("/v1/device-stream", Headers())) == HTTPStatus.UNAUTHORIZED
    assert auth_calls == ["policy", "stream"]


def test_cli_passes_explicit_lan_addresses(tmp_path, monkeypatch) -> None:
    identity = trustme.CA().issue_cert("192.168.1.10")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    identity.cert_chain_pems[0].write_to_path(cert)
    identity.private_key_pem.write_to_path(key)
    db = tmp_path / "db.sqlite"
    monkeypatch.setenv("STACKCHAN_SECURITY_PEPPER", "test-pepper")
    calls = []

    async def capture_start(db_path, pepper, tls, port, generation, host, device_ip):
        calls.append((db_path, host, device_ip, port, generation, tls.minimum_version))

    monkeypatch.setattr(cli, "_serve", capture_start)
    assert cli.main([
        "serve-device", "--security-db", str(db), "--cert", str(cert), "--key", str(key),
        "--port", "8443", "--generation", "1", "--listen", "192.168.1.10", "--device-ip", "192.168.1.15",
    ]) == 0
    assert calls == [(db, "192.168.1.10", "192.168.1.15", 8443, 1, ssl.TLSVersion.TLSv1_2)]
