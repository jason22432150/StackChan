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

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BatchAck:
        """自 Coordinator HTTP JSON 還原 ACK。"""
        if not isinstance(payload, dict):
            raise TypeError("BatchAck payload 必須為 object")
        rejected_raw = payload.get("rejected") or []
        if not isinstance(rejected_raw, list):
            raise TypeError("rejected 必須為 list")
        rejected: list[dict[str, str]] = []
        for item in rejected_raw:
            if not isinstance(item, dict):
                raise TypeError("rejected 項目必須為 object")
            rejected.append({str(key): str(value) for key, value in item.items()})
        return cls(
            bridge_id=str(payload["bridge_id"]),
            epoch=str(payload["epoch"]),
            contiguous_acked_sequence=int(payload["contiguous_acked_sequence"]),
            accepted_event_ids=[str(item) for item in (payload.get("accepted_event_ids") or [])],
            missing_sequences=[int(item) for item in (payload.get("missing_sequences") or [])],
            duplicate_event_ids=[str(item) for item in (payload.get("duplicate_event_ids") or [])],
            rejected=rejected,
        )
