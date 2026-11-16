"""Bridge 儲存測試 fixtures。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from stackchan.bridge import BridgeStore


@pytest.fixture
def bridge_db(tmp_path: Path) -> BridgeStore:
    store = BridgeStore(tmp_path / "bridge.sqlite3")
    store.ensure_bridge("bridge_win_1", epoch="epoch-1")
    yield store
    store.close()


@pytest.fixture
def base_event() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "event_id": "evt_001",
        "observation_id": "obs_001",
        "bridge_id": "bridge_win_1",
        "adapter_id": "codex.hooks",
        "agent_id": "codex",
        "event_type": "task.started",
        "evidence_level": "observed",
        "privacy_class": "internal",
        "observed_at": "2026-11-16T12:00:00Z",
        "bridge_sequence": 1,
        "epoch": "epoch-1",
    }
