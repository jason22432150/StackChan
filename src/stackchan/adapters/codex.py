"""
Codex CLI Adapter（官方 Hooks + legacy notify）。

證據原則：
- 官方 Hook／notify 視為 observed（非 verified；未對使用者實機 payload 升級）
- agent-turn-complete／Stop 對應 response.completed，**不得**推導 task.succeeded
- 不蒐集 Prompt、last_assistant_message、transcript 內容
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from stackchan.adapters.base import (
    AdapterCapability,
    AdapterError,
    MappedObservation,
    allowlist_scalars,
    pick_scalar,
)

_CODEX_CAPABILITY = AdapterCapability(
    adapter_id="codex.hooks",
    source_kind="native_hook",
    agent_id="codex",
    capabilities=("hooks", "legacy_notify"),
    event_semantics="official_hook_observed",
    confidence_baseline="observed",
    permissions=("read_hook_metadata",),
)

# 僅允許中性 metadata；刻意排除 input-messages／last-assistant-message／transcript_path
_NOTIFY_ALLOW = frozenset(
    {
        "type",
        "thread-id",
        "turn-id",
        "cwd",
        "client",
    }
)
_HOOK_ALLOW = frozenset(
    {
        "hook_event_name",
        "session_id",
        "turn_id",
        "cwd",
        "model",
        "permission_mode",
        "stop_hook_active",
        "agent_id",
        "agent_type",
        "source",
    }
)

# 即使誤入 allowlist 也強制剔除（密碼、Prompt、API Key、完整訊息）
_SENSITIVE_KEY_MARKERS = (
    "prompt",
    "message",
    "transcript",
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "token",
    "cookie",
)

# 明確忽略：不產生通知噪音的內部階段
_IGNORED_HOOKS = frozenset(
    {
        "PreCompact",
        "PostCompact",
        "precompact",
        "postcompact",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_hook_name(raw: Mapping[str, Any]) -> str | None:
    name = pick_scalar(raw, "hook_event_name", "type")
    if name is None:
        return None
    return str(name).strip()


class CodexAdapter:
    """受授權 Codex Adapter。"""

    @property
    def capability(self) -> AdapterCapability:
        return _CODEX_CAPABILITY

    def map_event(self, raw: Mapping[str, Any]) -> MappedObservation | None:
        if not isinstance(raw, Mapping):
            raise AdapterError("Codex payload 必須為 object")

        hook_name = _normalize_hook_name(raw)
        if hook_name is None:
            raise AdapterError("缺少 hook_event_name／type")

        if hook_name in _IGNORED_HOOKS:
            return None

        observed_at = _utc_now()

        # legacy notify：agent-turn-complete
        if hook_name in {"agent-turn-complete", "agent_turn_complete"}:
            thread_id = pick_scalar(raw, "thread-id", "thread_id")
            turn_id = pick_scalar(raw, "turn-id", "turn_id")
            if not thread_id or not turn_id:
                raise AdapterError("agent-turn-complete 需要 thread-id 與 turn-id")
            return MappedObservation(
                event_type="response.completed",
                evidence_level="observed",
                privacy_class="internal",
                source_event_id=f"codex:notify:{thread_id}:{turn_id}",
                session_id=str(thread_id),
                source_task_id=str(turn_id),
                observed_at=observed_at,
                source_payload=_sanitize_payload(allowlist_scalars(raw, _NOTIFY_ALLOW)),
            )

        session_id = pick_scalar(raw, "session_id", "thread_id", "thread-id")
        turn_id = pick_scalar(raw, "turn_id", "turn-id")
        event_type, evidence = _map_hook_event(hook_name)
        source_event_id = _source_event_id(hook_name, session_id, turn_id, raw)

        return MappedObservation(
            event_type=event_type,
            evidence_level=evidence,
            privacy_class="internal",
            source_event_id=source_event_id,
            session_id=str(session_id) if session_id is not None else None,
            source_task_id=str(turn_id) if turn_id is not None else None,
            observed_at=observed_at,
            source_payload=_sanitize_payload(allowlist_scalars(raw, _HOOK_ALLOW)),
        )


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """二次過濾：移除名稱像機密／Prompt 的鍵。"""
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = key.lower().replace("-", "_")
        if any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS):
            continue
        cleaned[key] = value
    return cleaned


def _map_hook_event(hook_name: str) -> tuple[str, str]:
    """Hook 名稱 → (event_type, evidence_level)。"""
    normalized = hook_name.strip()
    table: dict[str, tuple[str, str]] = {
        "SessionStart": ("task.started", "observed"),
        "sessionstart": ("task.started", "observed"),
        "SessionEnd": ("observation.uncertain", "observed"),
        "sessionend": ("observation.uncertain", "observed"),
        "Stop": ("response.completed", "observed"),
        "stop": ("response.completed", "observed"),
        "PermissionRequest": ("task.awaiting_user", "observed"),
        "permissionrequest": ("task.awaiting_user", "observed"),
        "PreToolUse": ("task.running", "observed"),
        "pretooluse": ("task.running", "observed"),
        "PostToolUse": ("task.running", "observed"),
        "posttooluse": ("task.running", "observed"),
        "UserPromptSubmit": ("task.running", "observed"),
        "userpromptsubmit": ("task.running", "observed"),
        "SubagentStart": ("task.started", "observed"),
        "subagentstart": ("task.started", "observed"),
        "SubagentStop": ("response.completed", "observed"),
        "subagentstop": ("response.completed", "observed"),
    }
    if normalized in table:
        return table[normalized]
    # 未知官方以外事件：保守降級
    return ("observation.uncertain", "unknown")


def _source_event_id(
    hook_name: str,
    session_id: Any,
    turn_id: Any,
    raw: Mapping[str, Any],
) -> str:
    parts = ["codex", hook_name]
    if session_id is not None:
        parts.append(str(session_id))
    if turn_id is not None:
        parts.append(str(turn_id))
    agent_id = pick_scalar(raw, "agent_id")
    if agent_id is not None:
        parts.append(str(agent_id))
    return ":".join(parts)
