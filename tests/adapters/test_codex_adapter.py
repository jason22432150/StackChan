"""Codex Adapter：事件轉換與證據等級。"""

from __future__ import annotations

import pytest

from stackchan.adapters import AdapterError, CodexAdapter
from stackchan.contracts import implies_task_succeeded


@pytest.fixture
def adapter() -> CodexAdapter:
    return CodexAdapter()


def test_capability_declares_native_hook(adapter: CodexAdapter) -> None:
    cap = adapter.capability
    assert cap.adapter_id == "codex.hooks"
    assert cap.source_kind == "native_hook"
    assert "hooks" in cap.capabilities
    assert cap.confidence_baseline == "observed"


def test_legacy_notify_maps_to_response_completed_not_succeeded(
    adapter: CodexAdapter,
) -> None:
    raw = {
        "type": "agent-turn-complete",
        "thread-id": "thread-1",
        "turn-id": "turn-9",
        "cwd": "/Users/example/project",
        "client": "codex-tui",
        "input-messages": ["Rename foo to bar"],
        "last-assistant-message": "Done.",
    }
    mapped = adapter.map_event(raw)
    assert mapped is not None
    assert mapped.event_type == "response.completed"
    assert mapped.evidence_level == "observed"
    assert mapped.source_event_id == "codex:notify:thread-1:turn-9"
    assert "input-messages" not in mapped.source_payload
    assert "last-assistant-message" not in mapped.source_payload
    assert not implies_task_succeeded(
        {"event_type": mapped.event_type, "evidence_level": mapped.evidence_level}
    )


def test_stop_hook_is_response_completed(adapter: CodexAdapter) -> None:
    mapped = adapter.map_event(
        {
            "hook_event_name": "Stop",
            "session_id": "sess-1",
            "turn_id": "t1",
            "cwd": "F:/project",
            "model": "gpt-5",
            "permission_mode": "default",
            "stop_hook_active": False,
            "last_assistant_message": "secret reply",
        }
    )
    assert mapped is not None
    assert mapped.event_type == "response.completed"
    assert mapped.evidence_level == "observed"
    assert "last_assistant_message" not in mapped.source_payload


def test_session_start_and_permission_request(adapter: CodexAdapter) -> None:
    started = adapter.map_event(
        {
            "hook_event_name": "SessionStart",
            "session_id": "sess-2",
            "cwd": "F:/repo",
            "model": "gpt-5",
            "source": "cli",
        }
    )
    assert started is not None
    assert started.event_type == "task.started"

    awaiting = adapter.map_event(
        {
            "hook_event_name": "PermissionRequest",
            "session_id": "sess-2",
            "turn_id": "t2",
            "cwd": "F:/repo",
        }
    )
    assert awaiting is not None
    assert awaiting.event_type == "task.awaiting_user"
    assert awaiting.evidence_level == "observed"


def test_precompact_ignored(adapter: CodexAdapter) -> None:
    assert adapter.map_event({"hook_event_name": "PreCompact", "session_id": "s"}) is None


def test_unknown_hook_degrades_to_uncertain(adapter: CodexAdapter) -> None:
    mapped = adapter.map_event({"hook_event_name": "FutureExotic", "session_id": "s"})
    assert mapped is not None
    assert mapped.event_type == "observation.uncertain"
    assert mapped.evidence_level == "unknown"


def test_missing_type_rejected(adapter: CodexAdapter) -> None:
    with pytest.raises(AdapterError):
        adapter.map_event({"cwd": "/tmp"})
