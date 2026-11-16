"""Cursor Adapter：事件轉換與證據等級。"""

from __future__ import annotations

import pytest

from stackchan.adapters import AdapterError, CursorAdapter
from stackchan.contracts import implies_task_succeeded


@pytest.fixture
def adapter() -> CursorAdapter:
    return CursorAdapter()


def test_capability(adapter: CursorAdapter) -> None:
    cap = adapter.capability
    assert cap.adapter_id == "cursor.hooks"
    assert cap.agent_id == "cursor"
    assert cap.source_kind == "native_hook"


def test_stop_completed_is_response_completed_not_succeeded(
    adapter: CursorAdapter,
) -> None:
    mapped = adapter.map_event(
        {
            "hook_event_name": "stop",
            "conversation_id": "conv-1",
            "generation_id": "gen-1",
            "status": "completed",
            "loop_count": 0,
            "cursor_version": "1.7.2",
            "user_email": "user@example.com",
            "transcript_path": "C:/secret/transcript.jsonl",
        }
    )
    assert mapped is not None
    assert mapped.event_type == "response.completed"
    assert mapped.evidence_level == "observed"
    assert "user_email" not in mapped.source_payload
    assert "transcript_path" not in mapped.source_payload
    assert not implies_task_succeeded({"event_type": mapped.event_type})


def test_stop_error_and_aborted(adapter: CursorAdapter) -> None:
    failed = adapter.map_event(
        {
            "hook_event_name": "stop",
            "conversation_id": "c",
            "generation_id": "g",
            "status": "error",
        }
    )
    assert failed is not None
    assert failed.event_type == "task.failed"

    cancelled = adapter.map_event(
        {
            "hook_event_name": "stop",
            "conversation_id": "c",
            "generation_id": "g2",
            "status": "aborted",
        }
    )
    assert cancelled is not None
    assert cancelled.event_type == "task.cancelled"


def test_session_start_and_tool_running(adapter: CursorAdapter) -> None:
    started = adapter.map_event(
        {
            "hook_event_name": "sessionStart",
            "conversation_id": "c1",
            "generation_id": "g0",
            "is_background_agent": False,
        }
    )
    assert started is not None
    assert started.event_type == "task.started"

    running = adapter.map_event(
        {
            "hook_event_name": "preToolUse",
            "conversation_id": "c1",
            "generation_id": "g1",
            "tool_name": "Shell",
            "tool_use_id": "tu-1",
            "tool_input": {"command": "npm install"},
            "cwd": "F:/project",
        }
    )
    assert running is not None
    assert running.event_type == "task.running"
    assert "tool_input" not in running.source_payload
    assert running.source_payload.get("tool_name") == "Shell"


def test_ignored_hooks(adapter: CursorAdapter) -> None:
    assert adapter.map_event({"hook_event_name": "preCompact", "conversation_id": "c"}) is None


def test_missing_hook_name(adapter: CursorAdapter) -> None:
    with pytest.raises(AdapterError):
        adapter.map_event({"conversation_id": "c"})
