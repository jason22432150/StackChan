"""裝置 WebSocket hello／heartbeat／模式隔離測試。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app, get_device_hub
from app.protocol import make_envelope


def test_hello_heartbeat_and_push(client: TestClient, monkeypatch):
    hub = get_device_hub()
    hub.expected_token = ""
    monkeypatch.setattr(hub, "expected_token", "")

    with client.websocket_connect("/ws/device") as ws:
        ws.send_json(
            {
                "v": 1,
                "id": "hello-1",
                "type": "hello",
                "payload": {
                    "device_id": "device-test",
                    "firmware_version": "phase1",
                    "caps": ["text", "motion"],
                    "mode": "companion",
                },
            }
        )
        hello_ok = ws.receive_json()
        assert hello_ok["type"] == "hello.ok"
        assert hello_ok["payload"]["session_id"]
        assert hub.can_push_companion_ui() is True

        ws.send_json(
            {
                "v": 1,
                "id": "hb-1",
                "type": "heartbeat",
                "ts_ms": 123,
                "payload": {"uptime_ms": 1000, "state": "IDLE"},
            }
        )
        hb = ws.receive_json()
        assert hb["type"] == "heartbeat"

        # 透過 HTTP push 下發文字
        response = client.post(
            "/api/device/push",
            json={"type": "text.show", "payload": {"text": "你好", "partial": False}},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True
        pushed = ws.receive_json()
        assert pushed["type"] == "text.show"
        assert pushed["payload"]["text"] == "你好"

        # 非法動畫應被拒絕且不送出
        bad = client.post(
            "/api/device/push",
            json={"type": "animation.play", "payload": {"name": "format_disk"}},
        )
        assert bad.status_code == 409
        assert bad.json()["error"] == "bad_animation"


def test_push_rejected_without_session(client: TestClient):
    hub = get_device_hub()
    hub.set_mode("offline", active=False)
    hub.session.websocket = None
    hub.session.session_id = None
    response = client.post(
        "/api/device/push",
        json=make_envelope("text.show", {"text": "nope"}).to_dict(),
    )
    assert response.status_code == 409
    assert response.json()["error"] in {"not_companion", "not_connected"}


def test_token_required_when_configured(client: TestClient, monkeypatch):
    hub = get_device_hub()
    monkeypatch.setattr(hub, "expected_token", "secret-token")
    rejected = False
    try:
        with client.websocket_connect("/ws/device") as ws:
            ws.send_json({"v": 1, "id": "x", "type": "hello", "payload": {"device_id": "d"}})
            ws.receive_json()
    except Exception:
        rejected = True
    assert rejected is True

    with client.websocket_connect("/ws/device?token=secret-token") as ws:
        ws.send_json(
            {
                "v": 1,
                "id": "hello-ok-token",
                "type": "hello",
                "payload": {"device_id": "d-token", "mode": "companion"},
            }
        )
        assert ws.receive_json()["type"] == "hello.ok"


def test_factory_mode_blocks_push(client: TestClient):
    with client.websocket_connect("/ws/device") as ws:
        ws.send_json(
            {
                "v": 1,
                "id": "hello-2",
                "type": "hello",
                "payload": {"device_id": "d2", "mode": "companion"},
            }
        )
        assert ws.receive_json()["type"] == "hello.ok"
        ws.send_json(
            {
                "v": 1,
                "id": "mode-1",
                "type": "device.mode",
                "payload": {"mode": "factory_ai", "active": False},
            }
        )
        assert ws.receive_json()["type"] == "ack"
        response = client.post(
            "/api/device/push",
            json={"type": "text.show", "payload": {"text": "不應顯示"}},
        )
        assert response.status_code == 409
        assert response.json()["error"] == "not_companion"
