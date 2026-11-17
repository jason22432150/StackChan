"""P2-04 裝置 loopback 握手軟路徑：live TLS policy → 裝置標頭契約 → stream。

不燒錄、不量測 R-006；證明 Coordinator loopback 回傳的 Policy／stream
可被裝置韌體握手進入點（completeDeviceLoopbackHandshake）消費的欄位契約滿足。
"""

from __future__ import annotations

import asyncio
import json
import ssl
from pathlib import Path

import pytest
import trustme
from websockets.asyncio.client import connect

from stackchan.contracts.authz import ApiGate, TokenDirectory
from stackchan.contracts.validate import validate_device_stream_envelope
from stackchan.coordinator.device_stream_server import serve_device_stream
from stackchan.coordinator.mvp_dispatcher import create_mvp_notification_dispatcher
from stackchan.coordinator.policy_lease import DevicePolicyLeaseService
from stackchan.coordinator.policy_lease_server import serve_device_policy
from stackchan.coordinator.runtime_limits import CORE_S3_MVP_RUNTIME_LIMITS, validate_coordinator_runtime_limits
from stackchan.security.auth_bridge import StoreBackedTokenDirectory
from stackchan.security.identity import TokenHasher
from stackchan.security.policy import PolicyService
from stackchan.security.store import SecurityStore

ROOT = Path(__file__).resolve().parents[2]
HANDSHAKE_H = ROOT / "firmware/main/stackchan/notifications/device_loopback_handshake.h"
CHECKLIST = ROOT / "docs/stackchan-agent-spec/docs/09_DEVELOPMENT_CHECKLIST.md"


@pytest.fixture
def device_loopback_env(tmp_path):
    authority = trustme.CA()
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    authority.issue_cert("127.0.0.1").configure_cert(tls)
    client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    authority.configure_trust(client)
    with SecurityStore(tmp_path / "auth.sqlite", hasher=TokenHasher(pepper=b"device-handshake")) as store:
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
        dispatcher = create_mvp_notification_dispatcher(tokens, policies, stable_seconds=0.04)
        yield leases, dispatcher, tls, client


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


def test_firmware_exposes_device_loopback_handshake_entry() -> None:
    text = HANDSHAKE_H.read_text(encoding="utf-8")
    assert "completeDeviceLoopbackHandshake" in text
    assert "deviceLoopbackHandshakeLinked" in text
    assert "不開 socket" in text


def test_checklist_p204_handshake_soft_path_does_not_claim_r006() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    line = next(line for line in text.splitlines() if "**P2-04**" in line)
    # 若已勾完成，必須仍標明 R-006／實機未完成；本輪預期維持未勾。
    if line.startswith("- [x]"):
        assert "R-006" in line
        assert "未燒錄" in line or "實機" in line
    else:
        assert line.startswith("- [ ]")


def test_device_headers_complete_loopback_tls_handshake(device_loopback_env) -> None:
    """模擬裝置 StreamProvision Config 標頭對同一 loopback 完成憑證握手。"""
    leases, dispatcher, tls, client = device_loopback_env
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
            # 裝置 parsePolicyLeaseJson 所需的 OpenAPI Policy 形狀
            assert set(policy) >= {"policy_id", "version", "privacy_mode", "valid_until"}
            assert policy["version"] == "v1"
            assert policy["privacy_mode"] == "private"
            assert "revoked" not in policy or policy.get("revoked") is False

            # 裝置 provision 後會帶入的 stream 握手標頭（對齊 DeviceStreamTlsClient::Config）
            device_stream_headers = {
                "Authorization": "Bearer device-token",
                "X-StackChan-Device-Id": "device-a",
                "X-StackChan-Policy-Version": policy["version"],
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
                async with connect(
                    path, ssl=client, additional_headers=device_stream_headers, proxy=None,
                ) as socket:
                    async with asyncio.timeout(2):
                        while True:
                            frame = validate_device_stream_envelope(json.loads(await socket.recv()))
                            assert frame["policy_version"] == policy["version"]
                            assert frame["device_id"] == "device-a"
                            assert frame["generation"] == 1
                            if frame["type"] == "notification.intent":
                                assert frame["delivery_id"] == "d1"
                                break
                            assert frame["type"] == "heartbeat"

    asyncio.run(exercise())


def test_untrusted_ca_rejects_device_policy_handshake(device_loopback_env) -> None:
    leases, _, tls, _ = device_loopback_env
    untrusted = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # 不 configure_trust → 裝置未帶 Coordinator CA 時應失敗
    other = trustme.CA()
    other.configure_trust(untrusted)

    async def exercise() -> None:
        async with await serve_device_policy(leases, tls, port=0) as policy_server:
            policy_port = policy_server.sockets[0].getsockname()[1]
            with pytest.raises(ssl.SSLCertVerificationError):
                await _http_get(untrusted, policy_port, "/v1/devices/device-a/policy", "device-token")

    asyncio.run(exercise())
