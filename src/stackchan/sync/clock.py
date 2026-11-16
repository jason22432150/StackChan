"""
時鐘偏差與跨 Bridge 因果處理。

不變式（T-SYNC-04／架構）：
- 不得以 wall-clock `observed_at` 做跨 Bridge Last-Write-Wins
- 同 Bridge 內順序以 `(epoch, bridge_sequence)` 為準
- 跨 Bridge 矛盾證據標記 concurrent／conflict，保留原始事件
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


class ClockError(ValueError):
    """時鐘／因果分析輸入無效。"""


@dataclass(frozen=True, slots=True)
class ClockSkewReport:
    """兩筆觀測的時鐘偏差報告（僅供診斷，不作因果依據）。"""

    skew_seconds: float
    exceeds_threshold: bool
    earlier_event_id: str
    later_event_id: str


@dataclass(frozen=True, slots=True)
class CausalityReport:
    """任務因果分析結果。"""

    task_key: str
    ordered_by: str
    concurrent: bool
    conflict: bool
    bridge_ids: tuple[str, ...]
    statuses: tuple[str, ...]
    event_ids: tuple[str, ...]
    note: str


_TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
_CONFLICT_PAIRS = frozenset(
    {
        frozenset({"succeeded", "failed"}),
        frozenset({"succeeded", "running"}),
        frozenset({"succeeded", "started"}),
        frozenset({"succeeded", "awaiting_user"}),
        frozenset({"failed", "running"}),
        frozenset({"cancelled", "succeeded"}),
    }
)


def parse_observed_at(value: str) -> datetime:
    """解析 AgentEvent observed_at（需為 date-time）。"""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ClockError(f"無效 observed_at={value!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def sequence_order_key(event: Mapping[str, Any]) -> tuple[str, str, int]:
    """同 Bridge 追加式順序鍵；刻意不含 wall-clock。"""
    return (
        str(event["bridge_id"]),
        str(event["epoch"]),
        int(event["bridge_sequence"]),
    )


def measure_clock_skew(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    threshold_seconds: float = 300.0,
) -> ClockSkewReport:
    """
    量測兩事件 observed_at 偏差。

    結果僅供診斷／告警，**不得**單獨決定任務因果。
    """
    left_at = parse_observed_at(str(left["observed_at"]))
    right_at = parse_observed_at(str(right["observed_at"]))
    if left_at <= right_at:
        earlier, later = left, right
        skew = (right_at - left_at).total_seconds()
    else:
        earlier, later = right, left
        skew = (left_at - right_at).total_seconds()
    return ClockSkewReport(
        skew_seconds=skew,
        exceeds_threshold=skew > threshold_seconds,
        earlier_event_id=str(earlier["event_id"]),
        later_event_id=str(later["event_id"]),
    )


def analyze_task_causality(
    events: Sequence[Mapping[str, Any]],
    *,
    task_key: str,
    threshold_seconds: float = 300.0,
) -> CausalityReport:
    """
    分析同一 task_key 的事件因果。

    - 單一 Bridge：依 bridge_sequence 排序（非 observed_at）
    - 多 Bridge：視為可能 concurrent；狀態矛盾則 conflict
    """
    if not events:
        raise ClockError("events 不可為空")

    bridge_ids = tuple(sorted({str(event["bridge_id"]) for event in events}))
    statuses = tuple(str(event["event_type"]) for event in events)
    event_ids = tuple(str(event["event_id"]) for event in events)

    if len(bridge_ids) == 1:
        ordered = sorted(events, key=sequence_order_key)
        # 驗證若誤用 wall-clock 排序是否會與 sequence 不一致（診斷）
        by_clock = sorted(events, key=lambda e: parse_observed_at(str(e["observed_at"])))
        clock_differs = [e["event_id"] for e in by_clock] != [e["event_id"] for e in ordered]
        return CausalityReport(
            task_key=task_key,
            ordered_by="bridge_sequence",
            concurrent=False,
            conflict=False,
            bridge_ids=bridge_ids,
            statuses=tuple(str(e["event_type"]) for e in ordered),
            event_ids=tuple(str(e["event_id"]) for e in ordered),
            note=(
                "same_bridge_sequence_order"
                + ("; wall_clock_order_differs" if clock_differs else "")
            ),
        )

    # 跨 Bridge：量測 skew 但不據此裁決
    skew_notes: list[str] = []
    for index, left in enumerate(events):
        for right in events[index + 1 :]:
            if left["bridge_id"] == right["bridge_id"]:
                continue
            report = measure_clock_skew(
                left, right, threshold_seconds=threshold_seconds
            )
            if report.exceeds_threshold:
                skew_notes.append(
                    f"skew>{threshold_seconds}s:{report.earlier_event_id}/{report.later_event_id}"
                )

    conflict = _has_status_conflict(events)
    return CausalityReport(
        task_key=task_key,
        ordered_by="none_cross_bridge",
        concurrent=True,
        conflict=conflict,
        bridge_ids=bridge_ids,
        statuses=statuses,
        event_ids=event_ids,
        note=(
            "cross_bridge_no_wall_clock_lww"
            + ("; " + ",".join(skew_notes) if skew_notes else "")
            + ("; conflict" if conflict else "")
        ),
    )


def _normalize_status(event_type: str) -> str:
    """將 event_type 收斂成可比較的簡名。"""
    return (
        event_type.replace("task.", "")
        .replace("response.", "")
        .replace("observation.", "")
    )


def _has_status_conflict(events: Sequence[Mapping[str, Any]]) -> bool:
    """不同 Bridge 對同一任務出現矛盾終態／進行中 vs 成功。"""
    by_bridge: dict[str, set[str]] = {}
    for event in events:
        bridge_id = str(event["bridge_id"])
        status = _normalize_status(str(event["event_type"]))
        by_bridge.setdefault(bridge_id, set()).add(status)

    if len(by_bridge) < 2:
        return False

    weight = {
        "succeeded": 50,
        "failed": 40,
        "cancelled": 35,
        "completed": 30,
        "awaiting_user": 20,
        "running": 15,
        "started": 10,
        "uncertain": 5,
    }

    representatives = [
        max(statuses, key=lambda item: weight.get(item, 0))
        for statuses in by_bridge.values()
    ]
    for index, left in enumerate(representatives):
        for right in representatives[index + 1 :]:
            if left == right:
                continue
            if frozenset({left, right}) in _CONFLICT_PAIRS:
                return True
            # 任一終態與其他 Bridge 不同狀態 → 衝突
            if left in _TERMINAL or right in _TERMINAL:
                return True
    return False
