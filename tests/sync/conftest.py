"""P2-02 同步測試 fixtures。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from stackchan.bridge import BridgeStore
from stackchan.contracts.authz import ApiGate, Principal, TokenDirectory
from stackchan.coordinator import CoordinatorStore
from stackchan.sync import CoordinatorSyncApi, InMemorySyncTransport


@pytest.fixture
def token_dir() -> TokenDirectory:
    directory = TokenDirectory()
    directory.issue(
        "bridge-token",
        Principal(
            subject_id="bridge_win_1",
            subject_type="bridge",
            scopes=frozenset({"bridge:write", "bridge:sync"}),
        ),
    )
    directory.issue(
        "bridge-b-token",
        Principal(
            subject_id="bridge_win_2",
            subject_type="bridge",
            scopes=frozenset({"bridge:write", "bridge:sync"}),
        ),
    )
    return directory


@pytest.fixture
def auth_header() -> str:
    return "Bearer bridge-token"


@pytest.fixture
def bridge_store(tmp_path: Path) -> BridgeStore:
    store = BridgeStore(tmp_path / "bridge.sqlite3")
    store.ensure_bridge("bridge_win_1", epoch="epoch-1")
    yield store
    store.close()


@pytest.fixture
def coordinator_store(tmp_path: Path) -> CoordinatorStore:
    store = CoordinatorStore(tmp_path / "coordinator.sqlite3")
    yield store
    store.close()


@pytest.fixture
def sync_api(coordinator_store: CoordinatorStore, token_dir: TokenDirectory) -> CoordinatorSyncApi:
    return CoordinatorSyncApi(coordinator_store, ApiGate(token_dir))


@pytest.fixture
def transport(sync_api: CoordinatorSyncApi) -> InMemorySyncTransport:
    return InMemorySyncTransport(api=sync_api)


def make_event(
    seq: int,
    *,
    bridge_id: str = "bridge_win_1",
    epoch: str = "epoch-1",
    event_type: str = "task.running",
    observed_at: str = "2026-11-16T12:00:00Z",
    source_task_id: str = "task_abc",
    **extra: Any,
) -> dict[str, Any]:
    payload = {
        "schema_version": "0.1",
        "event_id": f"evt_{bridge_id}_{seq:03d}",
        "observation_id": f"obs_{bridge_id}_{seq:03d}",
        "bridge_id": bridge_id,
        "adapter_id": "codex.hooks",
        "agent_id": "codex",
        "source_task_id": source_task_id,
        "event_type": event_type,
        "evidence_level": "observed",
        "privacy_class": "internal",
        "observed_at": observed_at,
        "bridge_sequence": seq,
        "epoch": epoch,
    }
    payload.update(extra)
    return payload


def seed_bridge_events(store: BridgeStore, events: list[dict[str, Any]]) -> None:
    """依序寫入 Bridge Outbox。"""
    for event in events:
        store.ingest_event(deepcopy(event))
