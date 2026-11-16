"""
Bridge 端同步引擎：Outbox → 批次上傳 → 套用 ACK／缺口重送。

Coordinator 離線或 Fail-Closed 時僅保留 pending，絕不直送 CoreS3。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stackchan.bridge import BridgeStore, BridgeStoreError
from stackchan.sync.coordinator_api import SyncFailClosedError
from stackchan.sync.models import BatchAck, BatchInput
from stackchan.sync.transport import SyncTransport, SyncTransportError


@dataclass(frozen=True, slots=True)
class SyncRoundResult:
    """單次 sync_once 結果。"""

    attempted: bool
    uploaded_event_ids: list[str]
    ack: BatchAck | None
    error: str | None
    pending_remaining: int
    contiguous_acked_sequence: int


class BridgeSyncClient:
    """將 BridgeStore pending 事件同步至 Coordinator。"""

    def __init__(
        self,
        store: BridgeStore,
        *,
        bridge_id: str,
        transport: SyncTransport,
        authorization_header: str,
        batch_limit: int = 100,
    ) -> None:
        if batch_limit < 1 or batch_limit > 100:
            raise BridgeStoreError("batch_limit 必須在 1..100")
        self.store = store
        self.bridge_id = bridge_id
        self.transport = transport
        self.authorization_header = authorization_header
        self.batch_limit = batch_limit

    def sync_once(self) -> SyncRoundResult:
        """上傳一輪 pending；失敗時保留 Outbox。"""
        settings = self.store.get_settings(self.bridge_id)
        epoch = settings["current_epoch"]
        pending = self.store.list_pending(self.bridge_id, limit=self.batch_limit)
        if not pending:
            return SyncRoundResult(
                attempted=False,
                uploaded_event_ids=[],
                ack=None,
                error=None,
                pending_remaining=0,
                contiguous_acked_sequence=self.store.get_contiguous_acked(
                    self.bridge_id, epoch
                ),
            )

        # 僅允許本 bridge／epoch 的事件進入批次
        events = [
            event
            for event in pending
            if event.get("bridge_id") == self.bridge_id and event.get("epoch") == epoch
        ]
        if not events:
            return SyncRoundResult(
                attempted=False,
                uploaded_event_ids=[],
                ack=None,
                error="pending_epoch_mismatch",
                pending_remaining=len(pending),
                contiguous_acked_sequence=self.store.get_contiguous_acked(
                    self.bridge_id, epoch
                ),
            )

        event_ids = [str(event["event_id"]) for event in events]
        batch = BatchInput(bridge_id=self.bridge_id, epoch=epoch, events=events)
        self.store.mark_upload_attempts(event_ids)

        try:
            ack = self.transport.submit_batch(
                batch,
                authorization_header=self.authorization_header,
            )
        except SyncFailClosedError as exc:
            self.store.mark_upload_attempts(event_ids, error=str(exc))
            return SyncRoundResult(
                attempted=True,
                uploaded_event_ids=event_ids,
                ack=None,
                error=f"fail_closed:{exc.mode.value}",
                pending_remaining=len(self.store.list_pending(self.bridge_id)),
                contiguous_acked_sequence=self.store.get_contiguous_acked(
                    self.bridge_id, epoch
                ),
            )
        except SyncTransportError as exc:
            self.store.mark_upload_attempts(event_ids, error=str(exc))
            return SyncRoundResult(
                attempted=True,
                uploaded_event_ids=event_ids,
                ack=None,
                error=str(exc),
                pending_remaining=len(self.store.list_pending(self.bridge_id)),
                contiguous_acked_sequence=self.store.get_contiguous_acked(
                    self.bridge_id, epoch
                ),
            )

        return self._apply_ack(ack, epoch=epoch, uploaded_event_ids=event_ids)

    def _apply_ack(
        self,
        ack: BatchAck,
        *,
        epoch: str,
        uploaded_event_ids: list[str],
    ) -> SyncRoundResult:
        if ack.bridge_id != self.bridge_id or ack.epoch != epoch:
            raise BridgeStoreError("ACK bridge_id／epoch 不符")

        # 持久確認：accepted + duplicate 皆可視為已同步（冪等重送）
        confirmed = list(
            dict.fromkeys([*ack.accepted_event_ids, *ack.duplicate_event_ids])
        )
        # 缺口中的 sequence 對應事件不可標 acked（apply_batch_ack 會檢查）
        contiguous = self.store.apply_batch_ack(
            bridge_id=self.bridge_id,
            epoch=epoch,
            accepted_event_ids=confirmed,
            missing_sequences=ack.missing_sequences,
        )
        return SyncRoundResult(
            attempted=True,
            uploaded_event_ids=uploaded_event_ids,
            ack=ack,
            error=None,
            pending_remaining=len(self.store.list_pending(self.bridge_id)),
            contiguous_acked_sequence=contiguous,
        )
