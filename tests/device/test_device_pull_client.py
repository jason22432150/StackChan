"""裝置 pending pull client：對本機 Pi HTTP 真實請求。"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from stackchan.coordinator.pi_http import PiCoordinatorConfig, create_pi_server
from stackchan.device.cli import main as device_main
from stackchan.device.pull_client import DevicePullClient, DevicePullError


@pytest.fixture
def pi_http(tmp_path: Path):
    config = PiCoordinatorConfig(
        db_path=tmp_path / "coordinator.sqlite3",
        bridge_id="bridge_primary",
        bridge_token="pi-bridge-token",
        host="127.0.0.1",
        port=0,
        device_id="cores3_primary",
        device_token="pi-device-token",
    )
    server, store, _app = create_pi_server(config)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield {
            "base": f"http://{host}:{port}",
            "bridge_token": "pi-bridge-token",
            "device_token": "pi-device-token",
            "device_id": "cores3_primary",
            "store": store,
        }
    finally:
        server.shutdown()
        server.server_close()
        store.close()
        thread.join(timeout=2)


def _sample_event() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "event_id": "evt_device_pull_001",
        "observation_id": "obs_device_pull_001",
        "bridge_id": "bridge_primary",
        "adapter_id": "codex.hooks",
        "agent_id": "codex",
        "source_task_id": "task_pull",
        "event_type": "response.completed",
        "evidence_level": "observed",
        "privacy_class": "internal",
        "observed_at": "2026-11-18T12:00:00Z",
        "bridge_sequence": 1,
        "epoch": "epoch-pull-1",
    }


def _post_batch(base: str, token: str, event: dict[str, Any]) -> None:
    from urllib.request import Request, urlopen

    body = json.dumps(
        {"bridge_id": "bridge_primary", "epoch": "epoch-pull-1", "events": [event]}
    ).encode("utf-8")
    req = Request(
        f"{base}/v1/events/batch",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=3) as resp:
        assert resp.status == 200


def test_device_pull_client_returns_pending(pi_http: dict[str, Any]) -> None:
    _post_batch(pi_http["base"], pi_http["bridge_token"], _sample_event())
    client = DevicePullClient(
        base_url=pi_http["base"],
        device_id=pi_http["device_id"],
        device_token=pi_http["device_token"],
        timeout_seconds=3.0,
    )
    result = client.pull_pending(limit=10)
    assert result.ok
    assert len(result.items) == 1
    item = result.items[0]
    assert item["delivery_id"] == "dlv_evt_device_pull_001"
    assert item["device_id"] == "cores3_primary"
    assert "payload_json" not in item
    assert "input_messages" not in item


def test_device_pull_client_rejects_wrong_token(pi_http: dict[str, Any]) -> None:
    client = DevicePullClient(
        base_url=pi_http["base"],
        device_id=pi_http["device_id"],
        device_token="wrong",
        timeout_seconds=3.0,
    )
    with pytest.raises(DevicePullError) as exc:
        client.pull_pending()
    assert "unauthorized" in str(exc.value)


def test_device_cli_pull_pending(pi_http: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    _post_batch(pi_http["base"], pi_http["bridge_token"], _sample_event())
    rc = device_main(
        [
            "pull-pending",
            "--coordinator-url",
            pi_http["base"],
            "--device-id",
            pi_http["device_id"],
            "--token",
            pi_http["device_token"],
            "--limit",
            "5",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["delivers_to_cores3_ui"] is False
