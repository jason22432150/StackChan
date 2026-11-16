"""P1-04 Coordinator SQLite migration／投影／已讀／receipt 測試。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from stackchan.coordinator import CoordinatorStore, CoordinatorStoreError
from stackchan.coordinator.store import SCHEMA_VERSION


def test_migration_applies_schema_version_and_indexes(
    coordinator_db: CoordinatorStore,
) -> None:
    assert coordinator_db.schema_version() == SCHEMA_VERSION
    # 再呼叫 migrate 應保持冪等
    coordinator_db.migrate()
    assert coordinator_db.schema_version() == SCHEMA_VERSION

    indexes = coordinator_db.list_indexes()
    assert "idx_events_bridge_epoch_seq" in indexes
    assert "idx_task_projections_status" in indexes
    assert "idx_receipts_delivery" in indexes
    assert "idx_event_evidence_event" in indexes
    assert "idx_purged_events_bridge_epoch" in indexes


def test_append_only_batch_ingest_and_gap_cursor(
    coordinator_db: CoordinatorStore, sample_events: list[dict[str, Any]]
) -> None:
    # 先匯入 1 與 3，缺 2
    result = coordinator_db.ingest_event_batch(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        events=[sample_events[0], sample_events[2]],
    )
    assert result.accepted_event_ids == ["evt_001", "evt_003"]
    assert result.contiguous_acked_sequence == 1
    assert result.missing_sequences == [2]

    # 補 2 後游標推進到 3
    result2 = coordinator_db.ingest_event_batch(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        events=[sample_events[1]],
    )
    assert result2.accepted_event_ids == ["evt_002"]
    assert result2.contiguous_acked_sequence == 3
    assert result2.missing_sequences == []
    assert coordinator_db.get_sync_cursor("bridge_win_1", "epoch-1") == 3


def test_idempotent_duplicate_event_id(
    coordinator_db: CoordinatorStore, sample_events: list[dict[str, Any]]
) -> None:
    first = coordinator_db.ingest_event_batch(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        events=[sample_events[0]],
    )
    second = coordinator_db.ingest_event_batch(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        events=[sample_events[0]],
    )
    assert first.accepted_event_ids == ["evt_001"]
    assert second.duplicate_event_ids == ["evt_001"]
    assert second.accepted_event_ids == []


def test_response_completed_does_not_mark_task_succeeded(
    coordinator_db: CoordinatorStore, sample_events: list[dict[str, Any]]
) -> None:
    coordinator_db.ingest_event_batch(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        events=sample_events,
    )
    projection = coordinator_db.get_task_projection("task_abc")
    assert projection is not None
    assert projection["status"] == "response_completed"
    assert projection["succeeded"] is False

    succeeded_event = deepcopy(sample_events[0])
    succeeded_event.update(
        {
            "event_id": "evt_004",
            "observation_id": "obs_004",
            "bridge_sequence": 4,
            "event_type": "task.succeeded",
            "evidence_level": "verified",
        }
    )
    coordinator_db.ingest_event_batch(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        events=[succeeded_event],
    )
    projection = coordinator_db.get_task_projection("task_abc")
    assert projection is not None
    assert projection["succeeded"] is True
    assert projection["status"] == "succeeded"


def test_mark_read_version_conflict_and_success(
    coordinator_db: CoordinatorStore, sample_events: list[dict[str, Any]]
) -> None:
    coordinator_db.ingest_event_batch(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        events=[sample_events[0]],
    )
    result = coordinator_db.mark_read(
        "evt_001",
        operation_id="op_1",
        expected_version=0,
        read=True,
    )
    assert result.read is True
    assert result.version == 1

    with pytest.raises(CoordinatorStoreError):
        coordinator_db.mark_read(
            "evt_001",
            operation_id="op_2",
            expected_version=0,
            read=True,
        )

    result2 = coordinator_db.mark_read(
        "evt_001",
        operation_id="op_3",
        expected_version=1,
        read=True,
    )
    assert result2.version == 2


def test_receipt_idempotent_and_unique(
    coordinator_db: CoordinatorStore,
) -> None:
    receipt = {
        "schema_version": "0.1",
        "receipt_id": "rcp_001",
        "delivery_id": "dlv_001",
        "attempt_id": "att_001",
        "device_id": "cores3_001",
        "generation": 1,
        "status": "completed",
        "reported_at": "2026-11-16T12:05:00Z",
    }
    first = coordinator_db.submit_receipt(receipt)
    second = coordinator_db.submit_receipt(receipt)
    assert first.created is True
    assert second.created is False
    assert first.accepted is True

    conflict = deepcopy(receipt)
    conflict["status"] = "interrupted"
    with pytest.raises(CoordinatorStoreError):
        coordinator_db.submit_receipt(conflict)


def test_rejected_invalid_schema_does_not_advance_cursor(
    coordinator_db: CoordinatorStore, sample_events: list[dict[str, Any]]
) -> None:
    bad = deepcopy(sample_events[0])
    bad["schema_version"] = "9.9"
    result = coordinator_db.ingest_event_batch(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        events=[bad, sample_events[0]],
    )
    assert "evt_001" in result.accepted_event_ids
    assert result.rejected
    assert result.contiguous_acked_sequence == 1


def test_reopen_preserves_migrated_schema(tmp_path: Path) -> None:
    path = tmp_path / "coord.sqlite3"
    with CoordinatorStore(path) as store:
        assert store.schema_version() == SCHEMA_VERSION
    with CoordinatorStore(path) as store:
        assert store.schema_version() == SCHEMA_VERSION
        assert "idx_events_bridge_epoch_seq" in store.list_indexes()
        assert "idx_purged_events_bridge_epoch" in store.list_indexes()
