"""
Coordinator 批次同步 API 門面（契約層，非真實 HTTP）。

Gate G2：未授權拒絕、服務非 ACTIVE 時 Fail-Closed（不接受事件）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from stackchan.contracts import AuthorizationError, Principal
from stackchan.contracts.authz import ApiGate
from stackchan.coordinator import BatchIngestResult, CoordinatorStore, CoordinatorStoreError
from stackchan.sync.clock import analyze_task_causality
from stackchan.sync.models import BatchAck, BatchInput


class CoordinatorMode(str, Enum):
    """同步服務生命週期（對齊架構 ACTIVE／SUSPENDED／ERROR）。"""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RECOVERING = "RECOVERING"
    ERROR = "ERROR"


class SyncFailClosedError(RuntimeError):
    """Coordinator 不可用：拒絕同步，Bridge 必須保留 Outbox。"""

    def __init__(self, mode: CoordinatorMode, message: str) -> None:
        super().__init__(message)
        self.mode = mode
        self.message = message


@dataclass(frozen=True, slots=True)
class SyncStatus:
    """GET /v1/sync/status 回應素材。"""

    bridge_id: str
    epoch: str
    contiguous_acked_sequence: int
    accepted_event_ids: list[str]
    missing_sequences: list[int]


class CoordinatorSyncApi:
    """授權＋Fail-Closed＋批次匯入。"""

    def __init__(
        self,
        store: CoordinatorStore,
        gate: ApiGate,
        *,
        mode: CoordinatorMode = CoordinatorMode.ACTIVE,
    ) -> None:
        self.store = store
        self.gate = gate
        self.mode = mode

    def set_mode(self, mode: CoordinatorMode) -> None:
        """測試／營運切換服務狀態。"""
        self.mode = mode

    def _assert_active(self) -> None:
        if self.mode != CoordinatorMode.ACTIVE:
            raise SyncFailClosedError(
                self.mode,
                f"Coordinator mode={self.mode.value}：Fail-Closed，拒絕同步",
            )

    def submit_event_batch(
        self,
        batch: BatchInput,
        *,
        authorization_header: str | None,
    ) -> BatchAck:
        """
        POST /v1/events/batch

        授權成功且 ACTIVE 才持久化；ACK 僅在交易提交後回傳。
        """
        principal = self.gate.authorize(
            "POST",
            "/v1/events/batch",
            authorization_header,
        )
        self._assert_bridge_principal(principal, batch.bridge_id)
        self._assert_active()

        try:
            result = self.store.ingest_event_batch(
                bridge_id=batch.bridge_id,
                epoch=batch.epoch,
                events=batch.events,
            )
        except CoordinatorStoreError as exc:
            raise CoordinatorStoreError(str(exc)) from exc

        self._record_cross_bridge_conflicts(batch.events)
        return _ack_from_result(result)

    def get_sync_status(
        self,
        *,
        bridge_id: str,
        epoch: str,
        authorization_header: str | None,
    ) -> BatchAck:
        """GET /v1/sync/status?bridge_id=...（此處 epoch 顯式傳入）。"""
        principal = self.gate.authorize(
            "GET",
            "/v1/sync/status",
            authorization_header,
        )
        self._assert_bridge_principal(principal, bridge_id)
        self._assert_active()

        contiguous = self.store.get_sync_cursor(bridge_id, epoch)
        missing = self.store.list_missing_sequences(bridge_id, epoch)
        return BatchAck(
            bridge_id=bridge_id,
            epoch=epoch,
            contiguous_acked_sequence=contiguous,
            accepted_event_ids=[],
            missing_sequences=missing,
        )

    def _assert_bridge_principal(
        self,
        principal: Principal | None,
        bridge_id: str,
    ) -> None:
        if principal is None:
            raise AuthorizationError(
                "unauthorized",
                "批次同步不可匿名",
                http_status=401,
            )
        if principal.subject_type == "bridge" and principal.subject_id != bridge_id:
            raise AuthorizationError(
                "forbidden",
                f"憑證 bridge={principal.subject_id} 不可寫入 {bridge_id}",
                http_status=403,
            )

    def _record_cross_bridge_conflicts(self, events: list[dict[str, Any]]) -> None:
        """跨 Bridge 同 task 矛盾時寫入 evidence（不依 wall-clock LWW）。"""
        task_ids = {
            event.get("source_task_id")
            for event in events
            if isinstance(event.get("source_task_id"), str) and event.get("source_task_id")
        }
        for task_id in task_ids:
            related = self.store.list_events_for_source_task(str(task_id))
            if len({event["bridge_id"] for event in related}) < 2:
                continue
            report = analyze_task_causality(related, task_key=str(task_id))
            if report.conflict or report.concurrent:
                prefix = "conflict" if report.conflict else "concurrent"
                self.store.record_task_conflict(
                    task_key=str(task_id),
                    note=f"{prefix}:{report.note}",
                    event_ids=list(report.event_ids),
                    mark_projection_conflict=report.conflict,
                )


def _ack_from_result(result: BatchIngestResult) -> BatchAck:
    return BatchAck.from_ingest(
        bridge_id=result.bridge_id,
        epoch=result.epoch,
        accepted_event_ids=result.accepted_event_ids,
        duplicate_event_ids=result.duplicate_event_ids,
        rejected=result.rejected,
        contiguous_acked_sequence=result.contiguous_acked_sequence,
        missing_sequences=result.missing_sequences,
    )
