"""Bridge → Pi Coordinator 真實 HTTP 同步（本機 loopback）。"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from stackchan.bridge.cli import main as bridge_main
from stackchan.bridge.store import BridgeStore
from stackchan.coordinator.pi_http import PiCoordinatorConfig, create_pi_server
from stackchan.sync import BatchInput, BridgeSyncClient, HttpSyncTransport, SyncTransportError
from tests.sync.conftest import make_event, seed_bridge_events


@pytest.fixture
def pi_http(tmp_path: Path):
    config = PiCoordinatorConfig(
        db_path=tmp_path / "coordinator.sqlite3",
        bridge_id="bridge_primary",
        bridge_token="pi-bridge-token",
        host="127.0.0.1",
        port=0,
    )
    server, store, _app = create_pi_server(config)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield {
            "base": f"http://{host}:{port}",
            "token": "pi-bridge-token",
            "store": store,
            "db_path": config.db_path,
        }
    finally:
        server.shutdown()
        server.server_close()
        store.close()
        thread.join(timeout=2)


def test_http_sync_persists_on_pi_and_acks_outbox(tmp_path: Path, pi_http: dict[str, Any]) -> None:
    bridge_db = tmp_path / "bridge.sqlite3"
    bridge = BridgeStore(bridge_db)
    bridge.ensure_bridge("bridge_primary", epoch="epoch-1")
    seed_bridge_events(
        bridge,
        [
            make_event(1, bridge_id="bridge_primary", event_type="task.started"),
            make_event(2, bridge_id="bridge_primary", event_type="response.completed"),
        ],
    )

    client = BridgeSyncClient(
        bridge,
        bridge_id="bridge_primary",
        transport=HttpSyncTransport(pi_http["base"], timeout_seconds=3.0),
        authorization_header=f"Bearer {pi_http['token']}",
    )
    result = client.sync_once()
    assert result.error is None
    assert result.pending_remaining == 0
    assert result.contiguous_acked_sequence == 2
    assert result.ack is not None
    assert set(result.ack.accepted_event_ids) == {
        "evt_bridge_primary_001",
        "evt_bridge_primary_002",
    }
    assert pi_http["store"].get_sync_cursor("bridge_primary", "epoch-1") == 2

    # Bridge 端已清空 pending
    assert bridge.list_pending("bridge_primary") == []
    bridge.close()


def test_http_sync_network_down_keeps_pending(tmp_path: Path) -> None:
    bridge = BridgeStore(tmp_path / "bridge.sqlite3")
    bridge.ensure_bridge("bridge_primary", epoch="epoch-1")
    seed_bridge_events(bridge, [make_event(1, bridge_id="bridge_primary")])

    client = BridgeSyncClient(
        bridge,
        bridge_id="bridge_primary",
        transport=HttpSyncTransport("http://127.0.0.1:1", timeout_seconds=0.5),
        authorization_header="Bearer unused",
    )
    result = client.sync_once()
    assert result.error is not None
    assert result.pending_remaining == 1
    assert bridge.list_pending("bridge_primary")
    bridge.close()


def test_http_sync_unauthorized_keeps_pending(tmp_path: Path, pi_http: dict[str, Any]) -> None:
    bridge = BridgeStore(tmp_path / "bridge.sqlite3")
    bridge.ensure_bridge("bridge_primary", epoch="epoch-1")
    seed_bridge_events(bridge, [make_event(1, bridge_id="bridge_primary")])

    client = BridgeSyncClient(
        bridge,
        bridge_id="bridge_primary",
        transport=HttpSyncTransport(pi_http["base"], timeout_seconds=3.0),
        authorization_header="Bearer wrong-token",
    )
    result = client.sync_once()
    assert result.error is not None
    assert "unauthorized" in result.error
    assert result.pending_remaining == 1
    bridge.close()


def test_http_resync_is_idempotent_duplicate_ack(tmp_path: Path, pi_http: dict[str, Any]) -> None:
    bridge = BridgeStore(tmp_path / "bridge.sqlite3")
    bridge.ensure_bridge("bridge_primary", epoch="epoch-1")
    seed_bridge_events(bridge, [make_event(1, bridge_id="bridge_primary")])
    transport = HttpSyncTransport(pi_http["base"], timeout_seconds=3.0)
    client = BridgeSyncClient(
        bridge,
        bridge_id="bridge_primary",
        transport=transport,
        authorization_header=f"Bearer {pi_http['token']}",
    )
    first = client.sync_once()
    assert first.error is None
    assert first.pending_remaining == 0

    # 模擬 ACK 丟失後重送：Coordinator 以 duplicate 回覆（冪等）
    again = transport.submit_batch(
        BatchInput(
            bridge_id="bridge_primary",
            epoch="epoch-1",
            events=[make_event(1, bridge_id="bridge_primary")],
        ),
        authorization_header=f"Bearer {pi_http['token']}",
    )
    assert again.duplicate_event_ids == ["evt_bridge_primary_001"]
    assert again.accepted_event_ids == []
    bridge.close()


def test_bridge_cli_sync_to_pi(tmp_path: Path, pi_http: dict[str, Any], capsys) -> None:
    db = tmp_path / "bridge.sqlite3"
    assert bridge_main(["init", "--db", str(db), "--bridge-id", "bridge_primary"]) == 0
    capsys.readouterr()

    store = BridgeStore(db)
    seed_bridge_events(store, [make_event(1, bridge_id="bridge_primary", event_type="task.started")])
    store.close()

    code = bridge_main(
        [
            "sync",
            "--db",
            str(db),
            "--bridge-id",
            "bridge_primary",
            "--coordinator-url",
            pi_http["base"],
            "--token",
            pi_http["token"],
        ]
    )
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["pending_remaining"] == 0
    assert out["delivers_to_cores3"] is False
    assert out["contiguous_acked_sequence"] == 1


def test_http_transport_rejects_bad_url() -> None:
    with pytest.raises(ValueError):
        HttpSyncTransport("ftp://example")
    with pytest.raises(SyncTransportError, match="缺少 Authorization"):
        HttpSyncTransport("http://127.0.0.1:9").submit_batch(
            BatchInput(bridge_id="b", epoch="e", events=[]),
            authorization_header=None,
        )
