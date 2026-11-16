"""
Agent Adapter 共用契約。

Adapter 只負責「來源觀測 → 中立 MappedObservation」；
BridgeService 再填入 bridge_id／sequence／epoch 並寫入 Outbox。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


class AdapterError(ValueError):
    """來源事件無法對應或違反授權邊界。"""


@dataclass(frozen=True, slots=True)
class AdapterCapability:
    """Adapter 對外宣告的能力與證據基線。"""

    adapter_id: str
    source_kind: str
    agent_id: str
    capabilities: tuple[str, ...]
    event_semantics: str
    confidence_baseline: str
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MappedObservation:
    """Adapter 轉換後、尚未綁定 Bridge sequence 的觀測。"""

    event_type: str
    evidence_level: str
    privacy_class: str
    source_event_id: str | None
    session_id: str | None
    source_task_id: str | None
    observed_at: str
    source_payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: str | None = None


class AgentAdapter(Protocol):
    """受授權來源 Adapter。"""

    @property
    def capability(self) -> AdapterCapability:
        """公開 source_kind／capabilities／permissions。"""

    def map_event(self, raw: Mapping[str, Any]) -> MappedObservation | None:
        """
        將官方 Hook／notify payload 轉成 MappedObservation。

        Returns:
            MappedObservation；若事件屬明確忽略清單則回傳 None。
        """


def pick_scalar(
    raw: Mapping[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    """依序嘗試多個欄位名稱（相容 kebab／snake_case）。"""
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return default


def allowlist_scalars(
    raw: Mapping[str, Any],
    allowed: frozenset[str],
    *,
    max_items: int = 32,
) -> dict[str, Any]:
    """
    只保留白名單純量欄位，供 source_payload 使用。

    陣列／物件一律省略，避免 Prompt、tool_input、憑證落入事件。
    """
    out: dict[str, Any] = {}
    for key in sorted(allowed):
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        if len(out) >= max_items:
            break
    return out
