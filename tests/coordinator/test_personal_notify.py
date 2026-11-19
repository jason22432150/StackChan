"""個人版事件→通知佇列。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from stackchan.contracts import validate_notification_intent
from stackchan.coordinator.personal_notify import (
    build_personal_notification_intent,
    priority_for_event_type,
)
from stackchan.coordinator.store import CoordinatorStore


def _event(event_id: str, event_type: str = "response.completed") -> dict:
    return {
        "schema_version": "0.1",
        "event_id": event_id,
        "observation_id": f"obs_{event_id}",
        "bridge_id": "bridge_primary",
        "adapter_id": "codex.hooks",
        "agent_id": "codex",
        "source_task_id": "task_1",
        "event_type": event_type,
        "evidence_level": "observed",
        "privacy_class": "internal",
        "observed_at": "2026-11-18T12:00:00Z",
        "bridge_sequence": 1,
        "epoch": "epoch-1",
    }


def test_priority_mapping() -> None:
    assert priority_for_event_type("task.failed") > priority_for_event_type("response.completed")
    assert priority_for_event_type("response.completed") > priority_for_event_type("task.started")


def test_build_intent_is_contract_valid_and_a0() -> None:
    intent = build_personal_notification_intent(
        _event("evt_a"),
        device_id="cores3_primary",
        now=datetime(2026, 11, 19, 0, 0, tzinfo=timezone.utc),
    )
    assert validate_notification_intent(intent) == intent
    assert intent["presentation_policy"]["tts"] is False
    assert intent["presentation_policy"]["audio"] is False
    assert intent["presentation_policy"]["ui"] is True
    assert intent["presentation_policy"]["motion"] is True
    assert intent["priority"] == 60
    assert intent["expires_at"] == "2026-11-19T00:10:00Z"
    assert intent["policy_version"] == "pol_personal_v1"


def test_store_enqueue_list_dedup_and_ttl(tmp_path: Path) -> None:
    store = CoordinatorStore(tmp_path / "c.sqlite3")
    assert store.schema_version() >= 3
    # 固定未來時鐘，避免 list_pending 依牆上時間把 TTL 誤判過期
    clock = datetime(2099, 1, 1, 12, 0, tzinfo=timezone.utc)
    intent = build_personal_notification_intent(
        _event("evt_b"), device_id="cores3_primary", now=clock
    )
    assert store.enqueue_pending_notification(intent) is True
    assert store.enqueue_pending_notification(intent) is False
    items = store.list_pending_notifications(limit=10)
    assert len(items) == 1
    assert items[0]["delivery_id"] == intent["delivery_id"]
    assert items[0]["policy_version"] == "pol_personal_v1"

    other = build_personal_notification_intent(
        _event("evt_other"), device_id="cores3_other", now=clock
    )
    assert store.enqueue_pending_notification(other) is True
    scoped = store.list_pending_notifications(limit=10, device_id="cores3_primary")
    assert len(scoped) == 1
    assert scoped[0]["device_id"] == "cores3_primary"

    # 僅讓 primary 過期；other 仍在 TTL 內
    store._conn.execute(
        "UPDATE pending_notifications SET expires_at = ? WHERE delivery_id = ?",
        ("2020-01-01T00:00:00Z", intent["delivery_id"]),
    )
    assert store.expire_pending_notifications(now_iso="2099-01-01T12:00:00Z") == 1
    assert store.list_pending_notifications(limit=10, device_id="cores3_primary") == []
    assert len(store.list_pending_notifications(limit=10, device_id="cores3_other")) == 1
    store.close()
