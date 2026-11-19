"""PersonalPendingBootConfig 與 accept-boot 契約。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from stackchan.device.boot_config import BootConfigError, PersonalPendingBootConfig
from stackchan.device.cli import main as device_main


def test_from_env_parses_coordinator_url() -> None:
    cfg = PersonalPendingBootConfig.from_env(
        {
            "STACKCHAN_COORDINATOR_URL": "http://192.168.20.148:8443",
            "STACKCHAN_DEVICE_ID": "cores3_primary",
            "STACKCHAN_DEVICE_TOKEN": "a" * 32,
        }
    )
    assert cfg.coordinator_host == "192.168.20.148"
    assert cfg.port == 8443
    assert cfg.coordinator_base_url() == "http://192.168.20.148:8443"
    public = cfg.to_public_dict(now=datetime(2026, 11, 19, tzinfo=timezone.utc))
    assert public["device_token_len"] == 32
    assert public["nvs_namespace"] == "personal_pend"
    assert "device_token" not in public


def test_rejects_short_token() -> None:
    with pytest.raises(BootConfigError, match="device_token"):
        PersonalPendingBootConfig(
            coordinator_host="pi.local",
            port=8443,
            device_id="cores3_primary",
            device_token="short",
        )


def test_accept_boot_live_shape(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    class FakePull:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def pull_pending(self, *, limit: int = 50) -> object:
            assert limit == 5

            class R:
                ok = True
                device_id = "cores3_primary"
                items: list = []
                error = None

            return R()

    monkeypatch.setenv("STACKCHAN_COORDINATOR_URL", "http://192.168.20.148:8443")
    monkeypatch.setenv("STACKCHAN_DEVICE_ID", "cores3_primary")
    monkeypatch.setenv("STACKCHAN_DEVICE_TOKEN", "b" * 40)
    monkeypatch.setattr("stackchan.device.cli.DevicePullClient", FakePull)
    assert device_main(["accept-boot", "--limit", "5"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["device_token_accepted"] is True
    assert payload["boot"]["coordinator_host"] == "192.168.20.148"
    assert payload["nvs_namespace"] == "personal_pend"
    assert payload["flashed"] is False
