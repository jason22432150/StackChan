"""T-SYNC-04：多 Bridge 時鐘偏差不得武斷推導任務因果。"""

from __future__ import annotations

from stackchan.contracts.authz import ApiGate
from stackchan.coordinator import CoordinatorStore
from stackchan.sync import (
    BatchInput,
    CoordinatorSyncApi,
    analyze_task_causality,
    measure_clock_skew,
    sequence_order_key,
)
from tests.sync.conftest import make_event


def test_sequence_order_ignores_wall_clock() -> None:
    earlier_clock = make_event(
        2,
        observed_at="2026-11-16T11:00:00Z",
        event_type="task.running",
    )
    later_clock = make_event(
        1,
        observed_at="2026-11-16T12:00:00Z",
        event_type="task.started",
    )
    ordered = sorted([earlier_clock, later_clock], key=sequence_order_key)
    assert [event["bridge_sequence"] for event in ordered] == [1, 2]
    # 若誤用 wall-clock 會得到相反順序
    by_clock = sorted(
        [earlier_clock, later_clock],
        key=lambda event: event["observed_at"],
    )
    assert [event["bridge_sequence"] for event in by_clock] == [2, 1]


def test_measure_skew_exceeds_threshold_but_not_causal() -> None:
    left = make_event(1, bridge_id="bridge_win_1", observed_at="2026-11-16T12:00:00Z")
    right = make_event(
        1,
        bridge_id="bridge_win_2",
        observed_at="2026-11-16T12:10:00Z",
        event_id="evt_b2_001",
        observation_id="obs_b2_001",
    )
    skew = measure_clock_skew(left, right, threshold_seconds=300)
    assert skew.skew_seconds == 600
    assert skew.exceeds_threshold is True


def test_cross_bridge_conflict_not_resolved_by_clock(
    coordinator_store: CoordinatorStore,
    token_dir,
) -> None:
    api = CoordinatorSyncApi(coordinator_store, ApiGate(token_dir))
    # Bridge A：時鐘較晚，宣稱 succeeded
    event_a = make_event(
        1,
        bridge_id="bridge_win_1",
        event_type="task.succeeded",
        evidence_level="verified",
        observed_at="2026-11-16T12:10:00Z",
        source_task_id="task_shared",
    )
    # Bridge B：時鐘早 10 分鐘，仍 running（若 LWW 靠時鐘會被 A 蓋掉）
    event_b = make_event(
        1,
        bridge_id="bridge_win_2",
        event_type="task.running",
        observed_at="2026-11-16T12:00:00Z",
        source_task_id="task_shared",
        event_id="evt_bridge_win_2_001",
        observation_id="obs_bridge_win_2_001",
    )

    api.submit_event_batch(
        BatchInput(bridge_id="bridge_win_1", epoch="epoch-1", events=[event_a]),
        authorization_header="Bearer bridge-token",
    )
    api.submit_event_batch(
        BatchInput(bridge_id="bridge_win_2", epoch="epoch-1", events=[event_b]),
        authorization_header="Bearer bridge-b-token",
    )

    related = coordinator_store.list_events_for_source_task("task_shared")
    assert len(related) == 2
    report = analyze_task_causality(related, task_key="task_shared")
    assert report.concurrent is True
    assert report.conflict is True
    assert report.ordered_by == "none_cross_bridge"
    assert "no_wall_clock_lww" in report.note

    projection = coordinator_store.get_task_projection("task_shared")
    assert projection is not None
    assert projection["status"] == "conflict"
    assert projection["succeeded"] is False
