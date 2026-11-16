"""P2-01：BridgeService 整合 Codex／Cursor Adapter 寫入 Outbox。"""

from __future__ import annotations

from pathlib import Path

import pytest

from stackchan.adapters import CodexAdapter, CursorAdapter
from stackchan.bridge import BridgeService, BridgeStore
from stackchan.contracts import implies_task_succeeded, validate_agent_event


@pytest.fixture
def service(tmp_path: Path) -> BridgeService:
    store = BridgeStore(tmp_path / "bridge.sqlite3")
    store.ensure_bridge("bridge_win_1", epoch="epoch-1")
    svc = BridgeService(store, "bridge_win_1")
    yield svc
    store.close()


def test_codex_notify_ingested_and_validated(service: BridgeService) -> None:
    outcome = service.ingest_raw(
        CodexAdapter(),
        {
            "type": "agent-turn-complete",
            "thread-id": "th-1",
            "turn-id": "tu-1",
            "cwd": "F:/repo",
            "client": "codex-tui",
            "input-messages": ["do stuff"],
            "last-assistant-message": "done",
        },
    )
    assert outcome.skipped is False
    assert outcome.result is not None
    assert outcome.result.created is True
    assert outcome.event is not None
    validate_agent_event(outcome.event)
    assert outcome.event["event_type"] == "response.completed"
    assert outcome.event["evidence_level"] == "observed"
    assert not implies_task_succeeded(outcome.event)
    assert service.status()["pending_count"] == 1


def test_idempotent_reingest_same_source_event(service: BridgeService) -> None:
    raw = {
        "hook_event_name": "Stop",
        "session_id": "sess-a",
        "turn_id": "turn-a",
        "cwd": "F:/repo",
    }
    first = service.ingest_raw(CodexAdapter(), raw)
    second = service.ingest_raw(CodexAdapter(), raw)
    assert first.result is not None and first.result.created is True
    assert second.result is not None and second.result.created is False
    assert first.result.event_id == second.result.event_id
    assert service.status()["pending_count"] == 1
    assert service.status()["next_sequence"] == 2


def test_cursor_stop_completed_outbox(service: BridgeService) -> None:
    outcome = service.ingest_raw(
        CursorAdapter(),
        {
            "hook_event_name": "stop",
            "conversation_id": "conv-9",
            "generation_id": "gen-9",
            "status": "completed",
            "loop_count": 0,
            "cursor_version": "2.0.0",
        },
    )
    assert outcome.result is not None
    assert outcome.event is not None
    validate_agent_event(outcome.event)
    assert outcome.event["adapter_id"] == "cursor.hooks"
    assert outcome.event["event_type"] == "response.completed"


def test_ignored_hook_skips_without_outbox(service: BridgeService) -> None:
    outcome = service.ingest_raw(
        CursorAdapter(),
        {"hook_event_name": "preCompact", "conversation_id": "c"},
    )
    assert outcome.skipped is True
    assert service.status()["pending_count"] == 0
    assert service.status()["next_sequence"] == 1
