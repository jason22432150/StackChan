"""P1-06 版本化設定、保留清理與禁止重導入測試。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from stackchan.coordinator import CoordinatorStore
from stackchan.retention import (
    DEFAULT_RETENTION_DAYS,
    RETENTION_DAY_CANDIDATES,
    RetentionError,
    RetentionService,
)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _event(seq: int, ingested_offset_days: int) -> dict[str, Any]:
    observed = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc) - timedelta(
        days=ingested_offset_days
    )
    return {
        "schema_version": "0.1",
        "event_id": f"evt_{seq:03d}",
        "observation_id": f"obs_{seq:03d}",
        "bridge_id": "bridge_win_1",
        "adapter_id": "codex.hooks",
        "agent_id": "codex",
        "source_task_id": f"task_{seq}",
        "event_type": "task.started",
        "evidence_level": "observed",
        "privacy_class": "internal",
        "observed_at": _iso(observed),
        "bridge_sequence": seq,
        "epoch": "epoch-1",
    }


@pytest.fixture
def store(tmp_path) -> CoordinatorStore:
    db = CoordinatorStore(tmp_path / "coord.sqlite3")
    yield db
    db.close()


@pytest.fixture
def retention(store: CoordinatorStore) -> RetentionService:
    return RetentionService(store)


def test_versioned_retention_settings(retention: RetentionService, store: CoordinatorStore) -> None:
    assert DEFAULT_RETENTION_DAYS in RETENTION_DAY_CANDIDATES
    v1 = retention.ensure_default_settings()
    assert v1 == 1
    assert retention.get_retention_days() == DEFAULT_RETENTION_DAYS
    v2 = retention.set_retention_days(7)
    assert v2 == 2
    assert store.get_setting_version("retention_days") == 2
    assert retention.get_retention_days() == 7
    snapshot = retention.settings_snapshot()
    assert snapshot["default_is_locked_product_value"] is False
    with pytest.raises(RetentionError):
        retention.set_retention_days(10)


def test_cleanup_purges_old_acked_and_blocks_reimport(
    store: CoordinatorStore, retention: RetentionService
) -> None:
    retention.set_retention_days(7)
    # seq1/2 很舊，seq3 很新
    events = [_event(1, 30), _event(2, 20), _event(3, 1)]
    result = store.ingest_event_batch(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        events=events,
    )
    assert result.contiguous_acked_sequence == 3

    # 將舊事件的 ingested_at 調成足夠舊（ingest 用 now，需直接更新）
    old = _iso(datetime.now(timezone.utc) - timedelta(days=20))
    store._conn.execute(
        "UPDATE events SET ingested_at = ? WHERE event_id IN ('evt_001', 'evt_002')",
        (old,),
    )

    report = retention.run_cleanup(bridge_id="bridge_win_1", epoch="epoch-1")
    assert set(report.purged_event_ids) == {"evt_001", "evt_002"}
    assert report.watermark == 2
    assert store.get_sync_cursor("bridge_win_1", "epoch-1") == 3

    # 清理後游標不因假缺口崩壞
    remaining = store._conn.execute("SELECT event_id FROM events").fetchall()
    assert [row["event_id"] for row in remaining] == ["evt_003"]

    # 禁止重導入已清理事件
    reimport = store.ingest_event_batch(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        events=[events[0]],
    )
    assert reimport.accepted_event_ids == []
    assert any(
        item["event_id"] == "evt_001" and item["error"] == "event_purged_no_reimport"
        for item in reimport.rejected
    )


def test_cleanup_does_not_purge_beyond_contiguous_gap(
    store: CoordinatorStore, retention: RetentionService
) -> None:
    retention.set_retention_days(7)
    # 只匯入 1 與 3，缺口 2；contiguous=1
    store.ingest_event_batch(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        events=[_event(1, 30), _event(3, 30)],
    )
    assert store.get_sync_cursor("bridge_win_1", "epoch-1") == 1

    old = _iso(datetime.now(timezone.utc) - timedelta(days=40))
    store._conn.execute("UPDATE events SET ingested_at = ?", (old,))

    report = retention.run_cleanup(bridge_id="bridge_win_1", epoch="epoch-1")
    # 只能清到 contiguous=1；seq3 雖舊但超出連續游標，保留
    assert report.purged_event_ids == ["evt_001"]
    assert store.is_purged("evt_001") is True
    assert store.is_purged("evt_003") is False
    rows = store._conn.execute(
        "SELECT event_id FROM events ORDER BY bridge_sequence"
    ).fetchall()
    assert [row["event_id"] for row in rows] == ["evt_003"]
