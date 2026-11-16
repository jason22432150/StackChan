"""受授權 Agent Adapter（Codex／Cursor）。"""

from stackchan.adapters.base import (
    AdapterCapability,
    AdapterError,
    AgentAdapter,
    MappedObservation,
)
from stackchan.adapters.codex import CodexAdapter
from stackchan.adapters.cursor import CursorAdapter

ADAPTER_REGISTRY: dict[str, type] = {
    "codex": CodexAdapter,
    "codex.hooks": CodexAdapter,
    "cursor": CursorAdapter,
    "cursor.hooks": CursorAdapter,
}


def get_adapter(name: str) -> CodexAdapter | CursorAdapter:
    """依 CLI／設定名稱取得 Adapter 實例。"""
    key = (name or "").strip().lower()
    # 正規化別名
    aliases = {
        "codex": "codex",
        "codex.hooks": "codex",
        "cursor": "cursor",
        "cursor.hooks": "cursor",
    }
    resolved = aliases.get(key)
    if resolved is None:
        raise AdapterError(f"未授權或不支援的 adapter={name!r}")
    if resolved == "codex":
        return CodexAdapter()
    return CursorAdapter()


__all__ = [
    "ADAPTER_REGISTRY",
    "AdapterCapability",
    "AdapterError",
    "AgentAdapter",
    "CodexAdapter",
    "CursorAdapter",
    "MappedObservation",
    "get_adapter",
]
