"""批次同步契約模型（對齊 OpenAPI BatchInput／BatchAck）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class BatchInput:
    """Bridge → Coordinator 批次。"""

    bridge_id: str
    epoch: str
    events: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "bridge_id": self.bridge_id,
            "epoch": self.epoch,
            "events": self.events,
        }


@dataclass(frozen=True, slots=True)
class BatchAck:
    """Coordinator 持久化後才能發出的 ACK。"""

    bridge_id: str
    epoch: str
    contiguous_acked_sequence: int
    accepted_event_ids: list[str] = field(default_factory=list)
    missing_sequences: list[int] = field(default_factory=list)
    duplicate_event_ids: list[str] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bridge_id": self.bridge_id,
            "epoch": self.epoch,
            "contiguous_acked_sequence": self.contiguous_acked_sequence,
            "accepted_event_ids": list(self.accepted_event_ids),
            "missing_sequences": list(self.missing_sequences),
            "duplicate_event_ids": list(self.duplicate_event_ids),
            "rejected": list(self.rejected),
        }

    @classmethod
    def from_ingest(
        cls,
        *,
        bridge_id: str,
        epoch: str,
        accepted_event_ids: list[str],
        duplicate_event_ids: list[str],
        rejected: list[dict[str, str]],
        contiguous_acked_sequence: int,
        missing_sequences: list[int],
    ) -> BatchAck:
        return cls(
            bridge_id=bridge_id,
            epoch=epoch,
            contiguous_acked_sequence=contiguous_acked_sequence,
            accepted_event_ids=accepted_event_ids,
            missing_sequences=missing_sequences,
            duplicate_event_ids=duplicate_event_ids,
            rejected=rejected,
        )
