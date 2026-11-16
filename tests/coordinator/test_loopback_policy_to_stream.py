"""P2-04 Coordinator loopback：TLS GET policy → MVP dispatcher → device-stream。"""

from __future__ import annotations

import asyncio
import json
import ssl

import pytest
import trustme
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from stackchan.contracts.authz import ApiGate, TokenDirectory
from stackchan.contracts.validate import validate_device_stream_envelope, validate_notification_intent
from stackchan.coordinator.device_stream_server import serve_device_stream
from stackchan.coordinator.mvp_dispatcher import create_mvp_notification_dispatcher
from stackchan.coordinator.policy_lease import DevicePolicyLeaseService
from stackchan.coordinator.policy_lease_server import serve_device_policy
from stackchan.coordinator.runtime_limits import CORE_S3_MVP_RUNTIME_LIMITS, validate_coordinator_runtime_limits
from stackchan.security.auth_bridge import StoreBackedTokenDirectory
from stackchan.security.identity import TokenHasher
from stackchan.security.policy import PolicyService
from stackchan.security.store import SecurityStore


@pytest.fixture
def loopback_env(tmp_path):
    authority = trustme.CA()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    authority.issue_cert("127.0.0.1").configure_cert(tls)
    client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    authority.configure_trust(client)
    with SecurityStore(tmp_path / "auth.sqlite", hasher=TokenHasher(pepper=b"loopback-e2e")) as store:
        store.upsert_subject("device-a", "device", "CoreS3")
        store.issue_grant(
            grant_id="device-token",
            subject_id="device-a",
            subject_type="device",
            token_plaintext="device-token",
            scopes=["device:policy", "device:stream"],
            expires_at="2099-01-01T00:00:00Z",
        )
        policies = PolicyService(store)
        policies.publish(
            {
                "policy_id": "desk",
                "version": "v1",
                "privacy_mode": "private",
                "valid_until": "2099-01-01T00:00:00Z",
            }
        )
        policies.bind_device("device-a", "desk", "v1")
        tokens = StoreBackedTokenDirectory(store)
        leases = DevicePolicyLeaseService(ApiGate(tokens), policies)
        dispatcher = create_mvp_notification_dispatcher(
            tokens, policies, stable_seconds=0.04,
        )
        yield leases, dispatcher, tls, client, policies, tokens


async def _http_get(ssl_context: ssl.SSLContext, port: int, path: str, token: str) -> tuple[int, dict]:
    reader, writer = await asyncio.open_connection(
        "127.0.0.1", port, ssl=ssl_context, server_hostname="127.0.0.1",
    )
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: 127.0.0.1\r\n"
        f"Authorization: Bearer {token}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    writer.write(request)
    await writer.drain()
    raw = await reader.read()
    writer.close()
    await writer.wait_closed()
    header, _, body = raw.partition(b"\r\n\r\n")
    status = int(header.split(b"\r\n", 1)[0].decode("ascii").split()[1])
    return status, json.loads(body.decode("utf-8")) if body else {}


def test_mvp_dispatcher_rejects_capacity_above_ceiling(tmp_path) -> None:
    limits = validate_coordinator_runtime_limits(CORE_S3_MVP_RUNTIME_LIMITS)
    assert limits.device_queue_capacity == 4
    store = SecurityStore(tmp_path / "cap.sqlite", hasher=TokenHasher(pepper=b"cap"))
    policies = PolicyService(store)
    with pytest.raises(ValueError, match="capacity"):
        create_mvp_notification_dispatcher(TokenDirectory(), policies, capacity=5)
    store.close()


def test_loopback_policy_lease_opens_device_stream(loopback_env) -> None:
    leases, dispatcher, tls, client, _, _ = loopback_env
    intent = {
        "schema_version": "0.1",
        "notification_id": "n1",
        "delivery_id": "d1",
        "device_id": "device-a",
        "event_ids": ["e1"],
        "priority": 10,
        "policy_version": "v1",
        "generation": 1,
        "expires_at": "2099-01-01T00:00:00Z",
        "presentation_policy": {"ui": True, "audio": False, "motion": False, "tts": False},
    }
    assert dispatcher.enqueue(intent)

    async def exercise() -> None:
        async with await serve_device_policy(leases, tls, port=0) as policy_server:
            policy_port = policy_server.sockets[0].getsockname()[1]
            status, policy = await _http_get(
                client, policy_port, "/v1/devices/device-a/policy", "device-token",
            )
            assert status == 200
            assert policy == {
                "policy_id": "desk",
                "version": "v1",
                "privacy_mode": "private",
                "valid_until": "2099-01-01T00:00:00Z",
            }

            limits = validate_coordinator_runtime_limits(CORE_S3_MVP_RUNTIME_LIMITS)
            async with serve_device_stream(
                dispatcher,
                tls,
                port=0,
                generation=1,
                heartbeat_interval=0.02,
                pong_timeout=min(0.2, limits.pong_timeout_seconds),
            ) as stream_server:
                stream_port = stream_server.sockets[0].getsockname()[1]
                path = f"wss://127.0.0.1:{stream_port}/v1/device-stream"
                headers = {
                    "Authorization": "Bearer device-token",
                    "X-StackChan-Device-Id": "device-a",
                    "X-StackChan-Policy-Version": policy["version"],
                }
                with pytest.raises(InvalidStatus) as wrong:
                    async with connect(
                        path,
                        ssl=client,
                        additional_headers={**headers, "X-StackChan-Policy-Version": "wrong"},
                        proxy=None,
                    ):
                        pytest.fail("mismatched policy version accepted")
                assert wrong.value.response.status_code == 401

                async with connect(path, ssl=client, additional_headers=headers, proxy=None) as socket:
                    async with asyncio.timeout(2):
                        while True:
                            frame = validate_device_stream_envelope(json.loads(await socket.recv()))
                            if frame["type"] == "notification.intent":
                                assert frame["policy_version"] == policy["version"]
                                assert frame["delivery_id"] == "d1"
                                validate_notification_intent(frame["payload"])
                                break
                            assert frame["type"] == "heartbeat"
                            assert frame["policy_version"] == policy["version"]

    asyncio.run(exercise())
