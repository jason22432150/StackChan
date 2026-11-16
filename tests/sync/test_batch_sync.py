"""P2-02／Gate G2：批次同步、ACK 缺口、重送冪等、Fail-Closed。"""

from __future__ import annotations

import pytest

from stackchan.bridge import BridgeStore
from stackchan.contracts import AuthorizationError
from stackchan.coordinator import CoordinatorStore
from stackchan.sync import (
    BatchInput,
    BridgeSyncClient,
    CoordinatorMode,
    CoordinatorSyncApi,
    InMemorySyncTransport,
)
from tests.sync.conftest import make_event, seed_bridge_events


def test_happy_path_batch_sync_acks_outbox(
    bridge_store: BridgeStore,
    coordinator_store: CoordinatorStore,
    transport: InMemorySyncTransport,
    auth_header: str,
) -> None:
    events = [
        make_event(1, event_type="task.started"),
        make_event(2, event_type="task.running"),
        make_event(3, event_type="response.completed"),
    ]
    seed_bridge_events(bridge_store, events)

    client = BridgeSyncClient(
        bridge_store,
        bridge_id="bridge_win_1",
        transport=transport,
        authorization_header=auth_header,
    )
    result = client.sync_once()
    assert result.error is None
    assert result.contiguous_acked_sequence == 3
    assert result.pending_remaining == 0
    assert coordinator_store.get_sync_cursor("bridge_win_1", "epoch-1") == 3


def test_ack_gap_keeps_cursor_and_resends_missing(
    bridge_store: BridgeStore,
    coordinator_store: CoordinatorStore,
    sync_api: CoordinatorSyncApi,
    auth_header: str,
) -> None:
    seed_bridge_events(
        bridge_store,
        [
            make_event(1, event_type="task.started"),
            make_event(2, event_type="task.running"),
            make_event(3, event_type="response.completed"),
        ],
    )
    transport = InMemorySyncTransport(api=sync_api, drop_sequences={2})
    client = BridgeSyncClient(
        bridge_store,
        bridge_id="bridge_win_1",
        transport=transport,
        authorization_header=auth_header,
    )

    first = client.sync_once()
    assert first.error is None
    assert first.ack is not None
    assert first.ack.contiguous_acked_sequence == 1
    assert first.ack.missing_sequences == [2]
    assert first.contiguous_acked_sequence == 1
    assert first.pending_remaining == 1
    pending = bridge_store.list_pending("bridge_win_1")
    assert [event["bridge_sequence"] for event in pending] == [2]

    # 補送缺口
    transport.drop_sequences.clear()
    second = client.sync_once()
    assert second.error is None
    assert second.contiguous_acked_sequence == 3
    assert second.pending_remaining == 0
    assert coordinator_store.get_sync_cursor("bridge_win_1", "epoch-1") == 3


def test_ack_loss_resend_is_idempotent(
    bridge_store: BridgeStore,
    coordinator_store: CoordinatorStore,
    sync_api: CoordinatorSyncApi,
    auth_header: str,
) -> None:
    seed_bridge_events(bridge_store, [make_event(1, event_type="task.started")])
    transport = InMemorySyncTransport(api=sync_api, drop_ack=True)
    client = BridgeSyncClient(
        bridge_store,
        bridge_id="bridge_win_1",
        transport=transport,
        authorization_header=auth_header,
    )

    lost = client.sync_once()
    assert lost.error == "ack_lost_after_persist"
    assert lost.pending_remaining == 1
    # Coordinator 已持久化
    assert coordinator_store.get_sync_cursor("bridge_win_1", "epoch-1") == 1

    transport.drop_ack = False
    recovered = client.sync_once()
    assert recovered.error is None
    assert recovered.ack is not None
    assert recovered.ack.duplicate_event_ids == ["evt_bridge_win_1_001"]
    assert recovered.pending_remaining == 0
    assert recovered.contiguous_acked_sequence == 1
    # 不重複列
    related = coordinator_store.list_events_for_source_task("task_abc")
    assert len(related) == 1


def test_fail_closed_when_coordinator_suspended(
    bridge_store: BridgeStore,
    sync_api: CoordinatorSyncApi,
    auth_header: str,
) -> None:
    seed_bridge_events(bridge_store, [make_event(1)])
    sync_api.set_mode(CoordinatorMode.SUSPENDED)
    transport = InMemorySyncTransport(api=sync_api)
    client = BridgeSyncClient(
        bridge_store,
        bridge_id="bridge_win_1",
        transport=transport,
        authorization_header=auth_header,
    )
    result = client.sync_once()
    assert result.error == "fail_closed:SUSPENDED"
    assert result.pending_remaining == 1


def test_unauthorized_batch_rejected(
    sync_api: CoordinatorSyncApi,
) -> None:
    batch = BatchInput(
        bridge_id="bridge_win_1",
        epoch="epoch-1",
        events=[make_event(1)],
    )
    with pytest.raises(AuthorizationError):
        sync_api.submit_event_batch(batch, authorization_header=None)


def test_epoch_rotation_isolates_sequences(
    bridge_store: BridgeStore,
    coordinator_store: CoordinatorStore,
    transport: InMemorySyncTransport,
    auth_header: str,
) -> None:
    seed_bridge_events(bridge_store, [make_event(1, event_type="task.started")])
    client = BridgeSyncClient(
        bridge_store,
        bridge_id="bridge_win_1",
        transport=transport,
        authorization_header=auth_header,
    )
    assert client.sync_once().contiguous_acked_sequence == 1

    bridge_store.rotate_epoch("bridge_win_1", "epoch-2")
    seed_bridge_events(
        bridge_store,
        [make_event(1, epoch="epoch-2", event_type="task.running", event_id="evt_e2_001", observation_id="obs_e2_001")],
    )
    result = client.sync_once()
    assert result.error is None
    assert result.contiguous_acked_sequence == 1
    assert coordinator_store.get_sync_cursor("bridge_win_1", "epoch-1") == 1
    assert coordinator_store.get_sync_cursor("bridge_win_1", "epoch-2") == 1
