"""Coordinator 儲存測試 fixtures。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from stackchan.coordinator import CoordinatorStore


@pytest.fixture
def coordinator_db(tmp_path: Path) -> CoordinatorStore:
    store = CoordinatorStore(tmp_path / "coordinator.sqlite3")
    yield store
    store.close()


@pytest.fixture
def sample_events() -> list[dict[str, Any]]:
    def event(seq: int, event_type: str, **extra: Any) -> dict[str, Any]:
        payload = {
            "schema_version": "0.1",
            "event_id": f"evt_{seq:03d}",
            "observation_id": f"obs_{seq:03d}",
            "bridge_id": "bridge_win_1",
            "adapter_id": "codex.hooks",
            "agent_id": "codex",
            "source_task_id": "task_abc",
            "event_type": event_type,
            "evidence_level": "observed",
            "privacy_class": "internal",
            "observed_at": "2026-11-16T12:00:00Z",
            "bridge_sequence": seq,
            "epoch": "epoch-1",
        }
        payload.update(extra)
        return payload

    return [
        event(1, "task.started"),
        event(2, "task.running"),
        event(3, "response.completed", evidence_level="verified"),
    ]
