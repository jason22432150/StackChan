"""Pi Coordinator HTTP：健康檢查、授權、SQLite 持久化與 event_id 去重。"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from stackchan.coordinator import CoordinatorStore
from stackchan.coordinator.pi_http import PiCoordinatorConfig, create_pi_server


@pytest.fixture
def sample_event() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "event_id": "evt_pi_001",
        "observation_id": "obs_pi_001",
        "bridge_id": "bridge_primary",
        "adapter_id": "codex.hooks",
        "agent_id": "codex",
        "source_task_id": "task_pi",
        "event_type": "task.started",
        "evidence_level": "observed",
        "privacy_class": "internal",
        "observed_at": "2026-11-18T12:00:00Z",
        "bridge_sequence": 1,
        "epoch": "epoch-pi-1",
    }


@pytest.fixture
def pi_server(tmp_path: Path):
    db_path = tmp_path / "coordinator.sqlite3"
    config = PiCoordinatorConfig(
        db_path=db_path,
        bridge_id="bridge_primary",
        bridge_token="test-bridge-token",
        host="127.0.0.1",
        port=0,
    )
    server, store, app = create_pi_server(config)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        yield {
            "base": base,
            "db_path": db_path,
            "token": "test-bridge-token",
            "server": server,
            "store": store,
            "app": app,
        }
    finally:
        server.shutdown()
        server.server_close()
        store.close()
        thread.join(timeout=2)


def _request(
    base: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(f"{base}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return resp.status, payload
    except HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        return exc.code, payload


def test_healthz_does_not_require_token(pi_server: dict[str, Any]) -> None:
    status, payload = _request(pi_server["base"], "GET", "/healthz")
    assert status == 200
    assert payload["status"] == "ok"
    assert payload["service"] == "stackchan-pi-coordinator"


def test_batch_requires_bearer_token(pi_server: dict[str, Any], sample_event: dict[str, Any]) -> None:
    status, payload = _request(
        pi_server["base"],
        "POST",
        "/v1/events/batch",
        body={"bridge_id": "bridge_primary", "epoch": "epoch-pi-1", "events": [sample_event]},
    )
    assert status == 401
    assert payload["error"]["code"] == "unauthorized"


def test_batch_rejects_invalid_bearer_token(
    pi_server: dict[str, Any], sample_event: dict[str, Any]
) -> None:
    status, payload = _request(
        pi_server["base"],
        "POST",
        "/v1/events/batch",
        token="wrong-token",
        body={"bridge_id": "bridge_primary", "epoch": "epoch-pi-1", "events": [sample_event]},
    )
    assert status == 401
    assert payload["error"]["code"] == "unauthorized"


def test_batch_rejects_bridge_id_mismatch(
    pi_server: dict[str, Any], sample_event: dict[str, Any]
) -> None:
    foreign = dict(sample_event)
    foreign["bridge_id"] = "bridge_other"
    status, payload = _request(
        pi_server["base"],
        "POST",
        "/v1/events/batch",
        token=pi_server["token"],
        body={"bridge_id": "bridge_other", "epoch": "epoch-pi-1", "events": [foreign]},
    )
    assert status == 403
    assert payload["error"]["code"] == "forbidden"


def test_batch_persists_then_acks_and_dedups(
    pi_server: dict[str, Any], sample_event: dict[str, Any]
) -> None:
    batch = {
        "bridge_id": "bridge_primary",
        "epoch": "epoch-pi-1",
        "events": [sample_event],
    }
    status, ack = _request(
        pi_server["base"],
        "POST",
        "/v1/events/batch",
        token=pi_server["token"],
        body=batch,
    )
    assert status == 200
    assert ack["accepted_event_ids"] == ["evt_pi_001"]
    assert ack["contiguous_acked_sequence"] == 1
    assert ack["duplicate_event_ids"] == []

    status2, ack2 = _request(
        pi_server["base"],
        "POST",
        "/v1/events/batch",
        token=pi_server["token"],
        body=batch,
    )
    assert status2 == 200
    assert ack2["accepted_event_ids"] == []
    assert ack2["duplicate_event_ids"] == ["evt_pi_001"]
    assert ack2["contiguous_acked_sequence"] == 1

    status3, sync = _request(
        pi_server["base"],
        "GET",
        "/v1/sync/status?bridge_id=bridge_primary&epoch=epoch-pi-1",
        token=pi_server["token"],
    )
    assert status3 == 200
    assert sync["contiguous_acked_sequence"] == 1
    assert sync["missing_sequences"] == []


def test_sqlite_survives_process_reopen(
    tmp_path: Path, sample_event: dict[str, Any]
) -> None:
    """模擬容器重啟：關閉 server 後以同一 SQLite 檔再開，游標仍在。"""
    db_path = tmp_path / "coordinator.sqlite3"
    config = PiCoordinatorConfig(
        db_path=db_path,
        bridge_id="bridge_primary",
        bridge_token="test-bridge-token",
        host="127.0.0.1",
        port=0,
    )
    server, store, _app = create_pi_server(config)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    try:
        status, ack = _request(
            base,
            "POST",
            "/v1/events/batch",
            token="test-bridge-token",
            body={
                "bridge_id": "bridge_primary",
                "epoch": "epoch-pi-1",
                "events": [sample_event],
            },
        )
        assert status == 200
        assert ack["accepted_event_ids"] == ["evt_pi_001"]
    finally:
        server.shutdown()
        server.server_close()
        store.close()
        thread.join(timeout=2)

    reopened = CoordinatorStore(db_path)
    try:
        assert reopened.get_sync_cursor("bridge_primary", "epoch-pi-1") == 1
        again = reopened.ingest_event_batch(
            bridge_id="bridge_primary",
            epoch="epoch-pi-1",
            events=[sample_event],
        )
        assert again.duplicate_event_ids == ["evt_pi_001"]
        assert again.accepted_event_ids == []
    finally:
        reopened.close()


def test_compose_file_declares_sqlite_volume() -> None:
    """Compose 必須掛載具名 volume，確保 Pi 重啟後 SQLite 仍在。"""
    compose_path = Path(__file__).resolve().parents[2] / "deploy" / "pi" / "compose.yaml"
    compose = compose_path.read_text(encoding="utf-8")
    assert "coordinator-data:/data" in compose
    assert "STACKCHAN_BRIDGE_TOKEN" in compose
    assert "healthcheck:" in compose
    assert "/healthz" in compose
    assert "STACKCHAN_TLS" in compose
    assert "/dashboard" in compose


def test_dashboard_html_is_public_shell(pi_server: dict[str, Any]) -> None:
    req = Request(f"{pi_server['base']}/dashboard", method="GET")
    with urlopen(req, timeout=3) as resp:
        assert resp.status == 200
        assert "text/html" in resp.headers.get("Content-Type", "")
        body = resp.read().decode("utf-8")
    assert "stackchan-pi-coordinator" in body
    assert "test-bridge-token" not in body  # 不得嵌入真實 Token
    assert "/v1/events" in body


def test_list_events_requires_token_and_returns_summaries(
    pi_server: dict[str, Any], sample_event: dict[str, Any]
) -> None:
    status, payload = _request(pi_server["base"], "GET", "/v1/events?limit=10")
    assert status == 401
    assert payload["error"]["code"] == "unauthorized"

    status, _ack = _request(
        pi_server["base"],
        "POST",
        "/v1/events/batch",
        token=pi_server["token"],
        body={"bridge_id": "bridge_primary", "epoch": "epoch-pi-1", "events": [sample_event]},
    )
    assert status == 200

    status, listing = _request(
        pi_server["base"],
        "GET",
        "/v1/events?limit=10",
        token=pi_server["token"],
    )
    assert status == 200
    assert listing["next_cursor"] is None
    assert len(listing["items"]) == 1
    item = listing["items"][0]
    assert item["event_id"] == "evt_pi_001"
    assert item["event_type"] == "task.started"
    assert item["evidence_level"] == "observed"
    # 摘要不得夾帶完整 payload／可能敏感欄位名稱外的本文
    assert "payload_json" not in item
    assert "input_messages" not in item
    assert "last_assistant_message" not in item


def test_list_events_rejects_bad_limit(pi_server: dict[str, Any]) -> None:
    status, payload = _request(
        pi_server["base"],
        "GET",
        "/v1/events?limit=0",
        token=pi_server["token"],
    )
    assert status == 400
    assert payload["error"]["code"] == "bad_request"

    status, payload = _request(
        pi_server["base"],
        "GET",
        "/v1/events?limit=101",
        token=pi_server["token"],
    )
    assert status == 400
    assert payload["error"]["code"] == "bad_request"

    status, payload = _request(
        pi_server["base"],
        "GET",
        "/v1/events?limit=abc",
        token=pi_server["token"],
    )
    assert status == 400
    assert payload["error"]["code"] == "bad_request"


def test_list_events_rejects_wrong_token(pi_server: dict[str, Any]) -> None:
    status, payload = _request(
        pi_server["base"],
        "GET",
        "/v1/events?limit=10",
        token="wrong-token",
    )
    assert status == 401
    assert payload["error"]["code"] == "unauthorized"


def test_summarize_event_row_strips_sensitive_keys() -> None:
    from stackchan.coordinator.pi_dashboard import summarize_event_row

    row = {
        "event_id": "evt_1",
        "bridge_id": "bridge_primary",
        "epoch": "epoch-1",
        "bridge_sequence": 1,
        "event_type": "response.completed",
        "evidence_level": "observed",
        "privacy_class": "internal",
        "observed_at": "2026-11-18T12:00:00Z",
        "ingested_at": "2026-11-18T12:00:01Z",
        "payload_json": '{"secret":true}',
        "input_messages": ["do not leak"],
        "last_assistant_message": "nope",
    }
    summary = summarize_event_row(row)
    assert summary["event_id"] == "evt_1"
    assert "payload_json" not in summary
    assert "input_messages" not in summary
    assert "last_assistant_message" not in summary


def test_batch_enqueues_pending_notification(
    pi_server: dict[str, Any], sample_event: dict[str, Any]
) -> None:
    status, _ = _request(pi_server["base"], "GET", "/v1/notifications/pending")
    assert status == 401

    status, ack = _request(
        pi_server["base"],
        "POST",
        "/v1/events/batch",
        token=pi_server["token"],
        body={"bridge_id": "bridge_primary", "epoch": "epoch-pi-1", "events": [sample_event]},
    )
    assert status == 200
    assert ack["accepted_event_ids"] == ["evt_pi_001"]

    status, pending = _request(
        pi_server["base"],
        "GET",
        "/v1/notifications/pending?limit=10",
        token=pi_server["token"],
    )
    assert status == 200
    assert len(pending["items"]) == 1
    item = pending["items"][0]
    assert item["delivery_id"] == "dlv_evt_pi_001"
    assert item["event_ids"] == ["evt_pi_001"]
    assert item["presentation_policy"]["tts"] is False
    assert item["presentation_policy"]["audio"] is False
    assert item["presentation_policy"]["motion"] is True

    status, ack2 = _request(
        pi_server["base"],
        "POST",
        "/v1/events/batch",
        token=pi_server["token"],
        body={"bridge_id": "bridge_primary", "epoch": "epoch-pi-1", "events": [sample_event]},
    )
    assert status == 200
    assert ack2["duplicate_event_ids"] == ["evt_pi_001"]
    status, pending2 = _request(
        pi_server["base"],
        "GET",
        "/v1/notifications/pending?limit=10",
        token=pi_server["token"],
    )
    assert status == 200
    assert len(pending2["items"]) == 1
