"""P1-03 Bridge SQLite 交易、Outbox、epoch、斷電重試測試。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from stackchan.bridge import BridgeStore, BridgeStoreError


def make_event(base: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    event = deepcopy(base)
    event.update(overrides)
    return event


def test_atomic_ingest_writes_event_and_pending_outbox(
    bridge_db: BridgeStore, base_event: dict[str, Any]
) -> None:
    result = bridge_db.ingest_event(base_event)
    assert result.created is True
    assert result.bridge_sequence == 1
    pending = bridge_db.list_pending("bridge_win_1")
    assert len(pending) == 1
    assert pending[0]["event_id"] == "evt_001"
    assert bridge_db.get_settings("bridge_win_1")["next_sequence"] == 2


def test_idempotent_reingest_same_event(
    bridge_db: BridgeStore, base_event: dict[str, Any]
) -> None:
    first = bridge_db.ingest_event(base_event)
    second = bridge_db.ingest_event(base_event)
    assert first.created is True
    assert second.created is False
    assert len(bridge_db.list_pending("bridge_win_1")) == 1


def test_conflicting_payload_same_event_id_rejected(
    bridge_db: BridgeStore, base_event: dict[str, Any]
) -> None:
    bridge_db.ingest_event(base_event)
    conflict = make_event(base_event, event_type="task.failed")
    with pytest.raises(BridgeStoreError):
        bridge_db.ingest_event(conflict)


def test_sequence_must_be_contiguous(
    bridge_db: BridgeStore, base_event: dict[str, Any]
) -> None:
    bridge_db.ingest_event(base_event)
    skipped = make_event(
        base_event,
        event_id="evt_003",
        observation_id="obs_003",
        bridge_sequence=3,
    )
    with pytest.raises(BridgeStoreError):
        bridge_db.ingest_event(skipped)


def test_ack_contiguous_cursor_does_not_skip_gaps(
    bridge_db: BridgeStore, base_event: dict[str, Any]
) -> None:
    e1 = make_event(base_event)
    e2 = make_event(
        base_event,
        event_id="evt_002",
        observation_id="obs_002",
        bridge_sequence=2,
    )
    e3 = make_event(
        base_event,
        event_id="evt_003",
        observation_id="obs_003",
        bridge_sequence=3,
    )
    bridge_db.ingest_event(e1)
    bridge_db.ingest_event(e2)
    bridge_db.ingest_event(e3)

    # 101 與 103 成功、102 缺失 => 連續游標停在 1
    contiguous = bridge_db.apply_batch_ack(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        accepted_event_ids=["evt_001", "evt_003"],
        missing_sequences=[2],
    )
    assert contiguous == 1
    assert bridge_db.get_contiguous_acked("bridge_win_1", "epoch-1") == 1
    pending = {event["event_id"] for event in bridge_db.list_pending("bridge_win_1")}
    assert pending == {"evt_002"}

    contiguous = bridge_db.apply_batch_ack(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        accepted_event_ids=["evt_002"],
    )
    assert contiguous == 3
    assert bridge_db.list_pending("bridge_win_1") == []


def test_upload_attempt_increments_but_keeps_pending(
    bridge_db: BridgeStore, base_event: dict[str, Any]
) -> None:
    bridge_db.ingest_event(base_event)
    bridge_db.mark_upload_attempts(["evt_001"], error="network timeout")
    pending = bridge_db.list_pending("bridge_win_1")
    assert len(pending) == 1

    row = bridge_db._conn.execute(
        "SELECT attempt_count, last_error, status FROM outbox WHERE event_id = ?",
        ("evt_001",),
    ).fetchone()
    assert row["attempt_count"] == 1
    assert row["status"] == "pending"
    assert "timeout" in row["last_error"]


def test_rotate_epoch_resets_sequence(
    bridge_db: BridgeStore, base_event: dict[str, Any]
) -> None:
    bridge_db.ingest_event(base_event)
    bridge_db.rotate_epoch("bridge_win_1", "epoch-2")
    settings = bridge_db.get_settings("bridge_win_1")
    assert settings["current_epoch"] == "epoch-2"
    assert settings["next_sequence"] == 1

    next_event = make_event(
        base_event,
        event_id="evt_e2_001",
        observation_id="obs_e2_001",
        epoch="epoch-2",
        bridge_sequence=1,
    )
    result = bridge_db.ingest_event(next_event)
    assert result.epoch == "epoch-2"
    assert result.bridge_sequence == 1


def test_power_loss_before_commit_leaves_no_partial_rows(
    tmp_path: Path, base_event: dict[str, Any]
) -> None:
    db_path = tmp_path / "powerloss.sqlite3"
    store = BridgeStore(db_path)
    store.ensure_bridge("bridge_win_1", epoch="epoch-1")

    # 模擬交易中斷：寫入後 ROLLBACK（等同 commit 前斷電）
    store._conn.execute("BEGIN IMMEDIATE")
    store._conn.execute(
        """
        INSERT INTO observations(observation_id, adapter_id, observed_at, source_event_id, created_at)
        VALUES ('obs_x', 'codex.hooks', '2026-11-16T12:00:00Z', NULL, '2026-11-16T12:00:00Z')
        """
    )
    store._conn.execute("ROLLBACK")
    store.close()

    reopened = BridgeStore(db_path)
    reopened.ensure_bridge("bridge_win_1", epoch="epoch-1")
    assert reopened.list_pending("bridge_win_1") == []
    count = reopened._conn.execute("SELECT COUNT(*) AS c FROM observations").fetchone()["c"]
    assert count == 0
    # 正常 ingest 仍可用
    result = reopened.ingest_event(base_event)
    assert result.created is True
    reopened.close()


def test_power_loss_after_commit_keeps_pending_for_retry(
    tmp_path: Path, base_event: dict[str, Any]
) -> None:
    db_path = tmp_path / "retry.sqlite3"
    with BridgeStore(db_path) as store:
        store.ensure_bridge("bridge_win_1", epoch="epoch-1")
        store.ingest_event(base_event)
        store.mark_upload_attempts(["evt_001"], error="connection reset")

    # 重新開啟 = 斷電後重啟
    with BridgeStore(db_path) as store:
        pending = store.list_pending("bridge_win_1")
        assert len(pending) == 1
        assert pending[0]["event_id"] == "evt_001"
        store.mark_upload_attempts(["evt_001"], error="retry #2")
        contiguous = store.apply_batch_ack(
            bridge_id="bridge_win_1",
            epoch="epoch-1",
            accepted_event_ids=["evt_001"],
        )
        assert contiguous == 1
        assert store.list_pending("bridge_win_1") == []


def test_unique_observation_id_enforced(
    bridge_db: BridgeStore, base_event: dict[str, Any]
) -> None:
    bridge_db.ingest_event(base_event)
    duplicate_obs = make_event(
        base_event,
        event_id="evt_002",
        observation_id="obs_001",
        bridge_sequence=2,
    )
    with pytest.raises(BridgeStoreError):
        bridge_db.ingest_event(duplicate_obs)


def test_invalid_contract_rejected(
    bridge_db: BridgeStore, base_event: dict[str, Any]
) -> None:
    bad = deepcopy(base_event)
    bad["schema_version"] = "9.9"
    with pytest.raises(BridgeStoreError):
        bridge_db.ingest_event(bad)
