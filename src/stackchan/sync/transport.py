"""
同步傳輸抽象與可故障注入的記憶體 Transport（測試用）。

真實 HTTPS 部署屬後續；此層驗證 At-Least-Once＋冪等語意。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from stackchan.sync.coordinator_api import CoordinatorSyncApi, SyncFailClosedError
from stackchan.sync.models import BatchAck, BatchInput


class SyncTransportError(RuntimeError):
    """傳輸層暫時失敗（Bridge 應保留 pending 並重試）。"""


class SyncTransport(Protocol):
    """Bridge → Coordinator 傳輸介面。"""

    def submit_batch(
        self,
        batch: BatchInput,
        *,
        authorization_header: str | None,
    ) -> BatchAck:
        """送出批次；成功回傳持久 ACK。"""


@dataclass
class InMemorySyncTransport:
    """
    進程內 Transport，可模擬：
    - drop_sequences：從批次中丟棄指定 bridge_sequence（製造缺口）
    - drop_ack：Coordinator 已持久化但不回傳 ACK（ACK 丟失）
    - network_down：完全失敗
    """

    api: CoordinatorSyncApi
    drop_sequences: set[int] = field(default_factory=set)
    drop_ack: bool = False
    network_down: bool = False
    submit_count: int = 0

    def submit_batch(
        self,
        batch: BatchInput,
        *,
        authorization_header: str | None,
    ) -> BatchAck:
        self.submit_count += 1
        if self.network_down:
            raise SyncTransportError("network_down")

        events = [
            event
            for event in batch.events
            if int(event["bridge_sequence"]) not in self.drop_sequences
        ]
        if not events:
            raise SyncTransportError("batch_empty_after_drop")

        filtered = BatchInput(
            bridge_id=batch.bridge_id,
            epoch=batch.epoch,
            events=events,
        )
        try:
            ack = self.api.submit_event_batch(
                filtered,
                authorization_header=authorization_header,
            )
        except SyncFailClosedError:
            raise
        except Exception as exc:
            raise SyncTransportError(str(exc)) from exc

        if self.drop_ack:
            raise SyncTransportError("ack_lost_after_persist")
        return ack
