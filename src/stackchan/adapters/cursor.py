"""
Cursor IDE Adapter（官方 Agent Hooks）。

證據原則：
- 官方 hooks.json stdin payload 視為 observed
- stop.status=completed → response.completed（不得推導 task.succeeded）
- stop.status=error → task.failed；aborted → task.cancelled
- 不蒐集 prompt、tool_input／tool_output、user_email、transcript 內容
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

_CURSOR_CAPABILITY = AdapterCapability(
    adapter_id="cursor.hooks",
    source_kind="native_hook",
    agent_id="cursor",
    capabilities=("hooks",),
    event_semantics="official_hook_observed",
    confidence_baseline="observed",
    permissions=("read_hook_metadata",),
)

_ALLOW = frozenset(
    {
        "hook_event_name",
        "conversation_id",
        "generation_id",
        "cursor_version",
        "status",
        "final_status",
        "loop_count",
        "tool_name",
        "tool_use_id",
        "cwd",
        "duration",
        "is_background_agent",
        "composer_mode",
        "model",
    }
)

_IGNORED = frozenset(
    {
        "preCompact",
        "beforeTabFileRead",
        "afterTabFileEdit",
        "workspaceOpen",
        "afterAgentThought",
        "beforeReadFile",
        "beforeSubmitPrompt",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class CursorAdapter:
    """受授權 Cursor Adapter。"""

    @property
    def capability(self) -> AdapterCapability:
        return _CURSOR_CAPABILITY

    def map_event(self, raw: Mapping[str, Any]) -> MappedObservation | None:
        if not isinstance(raw, Mapping):
            raise AdapterError("Cursor payload 必須為 object")

        hook_name = pick_scalar(raw, "hook_event_name")
        if hook_name is None:
            raise AdapterError("缺少 hook_event_name")
        hook_name = str(hook_name).strip()

        if hook_name in _IGNORED:
            return None

        conversation_id = pick_scalar(raw, "conversation_id")
        generation_id = pick_scalar(raw, "generation_id")
        event_type, evidence = _map_hook(hook_name, raw)
        source_event_id = _source_event_id(hook_name, conversation_id, generation_id, raw)

        return MappedObservation(
            event_type=event_type,
            evidence_level=evidence,
            privacy_class="internal",
            source_event_id=source_event_id,
            session_id=str(conversation_id) if conversation_id is not None else None,
            source_task_id=str(generation_id) if generation_id is not None else None,
            observed_at=_utc_now(),
            source_payload=allowlist_scalars(raw, _ALLOW),
        )


def _map_hook(hook_name: str, raw: Mapping[str, Any]) -> tuple[str, str]:
    if hook_name == "sessionStart":
        return ("task.started", "observed")
    if hook_name == "sessionEnd":
        # final_status 僅作 metadata；語意仍保守
        return ("observation.uncertain", "observed")
    if hook_name == "stop":
        status = str(pick_scalar(raw, "status", default="") or "").lower()
        if status == "completed":
            return ("response.completed", "observed")
        if status == "error":
            return ("task.failed", "observed")
        if status == "aborted":
            return ("task.cancelled", "observed")
        return ("observation.uncertain", "unknown")
    if hook_name == "subagentStop":
        status = str(pick_scalar(raw, "status", default="") or "").lower()
        if status == "completed":
            return ("response.completed", "observed")
        if status == "error":
            return ("task.failed", "observed")
        if status in {"aborted", "cancelled"}:
            return ("task.cancelled", "observed")
        return ("response.completed", "observed")
    if hook_name in {
        "preToolUse",
        "postToolUse",
        "beforeShellExecution",
        "afterShellExecution",
        "beforeMCPExecution",
        "afterMCPExecution",
        "afterFileEdit",
        "afterAgentResponse",
        "subagentStart",
    }:
        return ("task.running", "observed")
    if hook_name == "postToolUseFailure":
        return ("task.running", "observed")
    return ("observation.uncertain", "unknown")


def _source_event_id(
    hook_name: str,
    conversation_id: Any,
    generation_id: Any,
    raw: Mapping[str, Any],
) -> str:
    parts = ["cursor", hook_name]
    if conversation_id is not None:
        parts.append(str(conversation_id))
    if generation_id is not None:
        parts.append(str(generation_id))
    tool_use_id = pick_scalar(raw, "tool_use_id")
    if tool_use_id is not None:
        parts.append(str(tool_use_id))
    status = pick_scalar(raw, "status")
    if status is not None and hook_name in {"stop", "subagentStop"}:
        parts.append(str(status))
    return ":".join(parts)
