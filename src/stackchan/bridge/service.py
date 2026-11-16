"""
Bridge 服務：Adapter 觀測 → 契約驗證 → SQLite Outbox。

本階段不直送 CoreS3；Coordinator 離線時僅本地保留。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from stackchan.adapters.base import AdapterError, AgentAdapter, MappedObservation
from stackchan.bridge.store import BridgeStore, BridgeStoreError, IngestResult
from stackchan.contracts import CONTRACT_SCHEMA_VERSION, assert_event_semantics


@dataclass(frozen=True, slots=True)
class BridgeIngestOutcome:
    """CLI／測試用寫入結果。"""

    result: IngestResult | None
    skipped: bool
    reason: str | None = None
    event: dict[str, Any] | None = None


class BridgeService:
    """單一 Bridge 實例的本機服務。"""

    def __init__(self, store: BridgeStore, bridge_id: str) -> None:
        if not bridge_id:
            raise BridgeStoreError("bridge_id 不可為空")
        self.store = store
        self.bridge_id = bridge_id
        self.store.ensure_bridge(bridge_id)

    def ingest_raw(
        self,
        adapter: AgentAdapter,
        raw: Mapping[str, Any],
    ) -> BridgeIngestOutcome:
        """將來源 payload 轉換並寫入 Outbox。"""
        try:
            mapped = adapter.map_event(raw)
        except AdapterError as exc:
            raise BridgeStoreError(str(exc)) from exc

        if mapped is None:
            return BridgeIngestOutcome(
                result=None,
                skipped=True,
                reason="adapter_ignored",
            )
        return self.ingest_mapped(adapter, mapped)

    def ingest_mapped(
        self,
        adapter: AgentAdapter,
        mapped: MappedObservation,
    ) -> BridgeIngestOutcome:
        """將已轉換觀測寫入；同來源事件冪等。"""
        cap = adapter.capability
        event_id, observation_id = _stable_ids(
            adapter_id=cap.adapter_id,
            mapped=mapped,
        )

        existing = self.store.get_event_by_id(event_id)
        if existing is not None:
            return BridgeIngestOutcome(
                result=IngestResult(
                    event_id=event_id,
                    observation_id=existing["observation_id"],
                    bridge_sequence=int(existing["bridge_sequence"]),
                    epoch=existing["epoch"],
                    created=False,
                ),
                skipped=False,
                event=existing,
            )

        settings = self.store.get_settings(self.bridge_id)
        event: dict[str, Any] = {
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "event_id": event_id,
            "observation_id": observation_id,
            "source_event_id": mapped.source_event_id,
            "bridge_id": self.bridge_id,
            "adapter_id": cap.adapter_id,
            "agent_id": cap.agent_id,
            "session_id": mapped.session_id,
            "source_task_id": mapped.source_task_id,
            "event_type": mapped.event_type,
            "evidence_level": mapped.evidence_level,
            "privacy_class": mapped.privacy_class,
            "observed_at": mapped.observed_at,
            "bridge_sequence": int(settings["next_sequence"]),
            "epoch": settings["current_epoch"],
            "source_payload": mapped.source_payload,
        }
        if mapped.occurred_at is not None:
            event["occurred_at"] = mapped.occurred_at

        # 語意閘：response.completed 不得被誤當 succeeded 路徑
        assert_event_semantics(event)
        result = self.store.ingest_event(event)
        return BridgeIngestOutcome(
            result=result,
            skipped=False,
            event=event,
        )

    def status(self) -> dict[str, Any]:
        """CLI status：設定與 pending 數量。"""
        settings = self.store.get_settings(self.bridge_id)
        pending = self.store.list_pending(self.bridge_id)
        return {
            "bridge_id": self.bridge_id,
            "current_epoch": settings["current_epoch"],
            "next_sequence": settings["next_sequence"],
            "pending_count": len(pending),
            "contiguous_acked_sequence": self.store.get_contiguous_acked(
                self.bridge_id,
                settings["current_epoch"],
            ),
        }


def _stable_ids(
    *,
    adapter_id: str,
    mapped: MappedObservation,
) -> tuple[str, str]:
    """以來源鍵產生穩定 event_id／observation_id（重送冪等）。"""
    material = "|".join(
        [
            adapter_id,
            mapped.source_event_id or "",
            mapped.event_type,
            mapped.evidence_level,
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    return f"evt_{digest}", f"obs_{digest}"


def dump_json(data: Any) -> str:
    """穩定 JSON 輸出（CLI）。"""
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
