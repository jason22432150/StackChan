import asyncio
import json
import ssl

import pytest
import trustme
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.frames import Opcode

from stackchan.contracts.validate import validate_device_stream_envelope, validate_notification_intent
from stackchan.coordinator.device_stream_server import serve_device_stream
from stackchan.coordinator.dispatch import NotificationDispatcher
from stackchan.security.auth_bridge import StoreBackedTokenDirectory
from stackchan.security.identity import TokenHasher
from stackchan.security.policy import PolicyService
from stackchan.security.store import SecurityStore


@pytest.fixture
def stream_config(tmp_path):
    authority = trustme.CA()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    authority.issue_cert("127.0.0.1").configure_cert(tls)
    client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    authority.configure_trust(client)
    with SecurityStore(tmp_path / "auth.sqlite", hasher=TokenHasher(pepper=b"test")) as store:
        store.upsert_subject("device-a", "device", "Test device")
        for token, scope in (("valid", "device:stream"), ("limited", "device:policy")):
            store.issue_grant(
                grant_id=token, subject_id="device-a", subject_type="device", token_plaintext=token,
                scopes=[scope], expires_at="2099-01-01T00:00:00Z",
            )
        policies = PolicyService(store)
        policies.publish({
            "policy_id": "policy", "version": "v1", "privacy_mode": "private",
            "valid_until": "2099-01-01T00:00:00Z",
        })
        policies.bind_device("device-a", "policy", "v1")
        tokens = StoreBackedTokenDirectory(store)
        dispatcher = NotificationDispatcher(
            tokens, policies, stable_seconds=0.04, heartbeat_timeout=1, capacity=4,
        )
        yield dispatcher, tls, client, tokens


def headers(token="valid", device="device-a", version="v1"):
    return {
        "Authorization": f"Bearer {token}",
        "X-StackChan-Device-Id": device,
        "X-StackChan-Policy-Version": version,
    }


def endpoint(server):
    return f"wss://127.0.0.1:{server.sockets[0].getsockname()[1]}"


def test_tls_upgrade_requires_trusted_certificate_and_device_scope(stream_config):
    dispatcher, tls, client, tokens = stream_config

    async def exercise():
        async with serve_device_stream(dispatcher, tls, port=0, generation=1,
                                       heartbeat_interval=0.02, pong_timeout=0.2) as server:
            base = endpoint(server)
            path = base + "/v1/device-stream"
            with pytest.raises(ssl.SSLCertVerificationError):
                async with connect(path, ssl=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT), proxy=None):
                    pytest.fail("untrusted certificate accepted")
            for auth in ({}, headers("limited"), headers(device="other"), headers(version="wrong")):
                with pytest.raises(InvalidStatus) as error:
                    async with connect(path, ssl=client, additional_headers=auth, proxy=None):
                        pytest.fail("unauthorized upgrade")
                assert error.value.response.status_code == 401
            with pytest.raises(InvalidStatus) as error:
                async with connect(path, ssl=client, additional_headers=headers(), origin="https://example.com", proxy=None):
                    pytest.fail("browser origin accepted")
            assert error.value.response.status_code == 403
            with pytest.raises(InvalidStatus) as error:
                async with connect(base + "/wrong", ssl=client, additional_headers=headers(), proxy=None):
                    pytest.fail("wrong path accepted")
            assert error.value.response.status_code == 404
            tokens.revoke("valid")
            with pytest.raises(InvalidStatus) as error:
                async with connect(path, ssl=client, additional_headers=headers(), proxy=None):
                    pytest.fail("revoked credential accepted")
            assert error.value.response.status_code == 401

    asyncio.run(exercise())


def test_tls_dispatch_sends_heartbeat_and_matching_intent_then_stops_on_revocation(stream_config):
    dispatcher, tls, client, tokens = stream_config
    intent = {
        "schema_version": "0.1", "notification_id": "notification", "delivery_id": "delivery",
        "device_id": "device-a", "event_ids": ["event"], "priority": 1, "policy_version": "v1",
        "generation": 2, "expires_at": "2099-01-01T00:00:00Z",
        "presentation_policy": {"ui": True, "audio": False, "motion": False, "tts": False},
    }
    assert dispatcher.enqueue({**intent, "delivery_id": "old", "generation": 1, "priority": 100})
    assert dispatcher.enqueue(intent)

    async def exercise():
        async with serve_device_stream(dispatcher, tls, port=0, generation=2,
                                       heartbeat_interval=0.02, pong_timeout=0.2) as server:
            path = endpoint(server) + "/v1/device-stream"
            async with connect(path, ssl=client, additional_headers=headers(), proxy=None) as socket:
                heartbeats = []
                async with asyncio.timeout(2):
                    while True:
                        wire = await socket.recv()
                        assert isinstance(wire, str)
                        frame = validate_device_stream_envelope(json.loads(wire))
                        assert frame["generation"] == 2
                        if frame["type"] == "notification.intent":
                            assert frame["delivery_id"] == "delivery"
                            validate_notification_intent(frame["payload"])
                            break
                        heartbeats.append(frame["sent_at"])
                assert len(heartbeats) >= 2
                assert heartbeats == sorted(set(heartbeats))
                tokens.revoke("valid")
                with pytest.raises(ConnectionClosed) as closed:
                    async with asyncio.timeout(2):
                        while True:
                            frame = json.loads(await socket.recv())
                            assert frame["type"] == "heartbeat"
                assert closed.value.rcvd.code == 1008

    asyncio.run(exercise())


def test_tls_transport_closes_when_device_stops_answering_ping(stream_config, monkeypatch):
    dispatcher, tls, client, _ = stream_config

    async def exercise():
        async with serve_device_stream(dispatcher, tls, port=0, generation=1,
                                       heartbeat_interval=0.02, pong_timeout=0.10) as server:
            path = endpoint(server) + "/v1/device-stream"
            async with connect(path, ssl=client, additional_headers=headers(), proxy=None) as socket:
                assert json.loads(await asyncio.wait_for(socket.recv(), 2))["type"] == "heartbeat"
                send_frame = socket.protocol.send_frame

                def drop_pong(frame):
                    if frame.opcode != Opcode.PONG:
                        send_frame(frame)

                monkeypatch.setattr(socket.protocol, "send_frame", drop_pong)
                with pytest.raises(ConnectionClosed) as closed:
                    await asyncio.wait_for(socket.recv(), 2)
                assert closed.value.rcvd.code == 1008
                assert closed.value.rcvd.reason == "Heartbeat timeout"

    asyncio.run(exercise())
