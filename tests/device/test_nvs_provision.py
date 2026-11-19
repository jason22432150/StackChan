"""personal_pend NVS 佈建 CLI／CSV 產物。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from stackchan.device.boot_config import PersonalPendingBootConfig
from stackchan.device.cli import main as device_main
from stackchan.device.nvs_provision import (
    NVS_NAMESPACE,
    NvsProvisionError,
    personal_pending_nvs_rows,
    redact_csv_for_display,
    render_nvs_csv,
    write_personal_pending_nvs_provision,
)


def _boot(**kwargs: object) -> PersonalPendingBootConfig:
    base = {
        "coordinator_host": "192.168.20.148",
        "port": 8443,
        "device_id": "cores3_primary",
        "device_token": "t" * 32,
    }
    base.update(kwargs)
    return PersonalPendingBootConfig(**base)  # type: ignore[arg-type]


def test_csv_rows_match_firmware_keys() -> None:
    rows = personal_pending_nvs_rows(_boot())
    assert rows[0].key == NVS_NAMESPACE and rows[0].type == "namespace"
    keys = [r.key for r in rows[1:]]
    assert keys == [
        "host",
        "port",
        "device_id",
        "token",
        "policy_ver",
        "generation",
        "session",
        "limit",
        "ttl_sec",
        "fetch_ms",
    ]
    text = render_nvs_csv(rows)
    assert text.startswith("key,type,encoding,value\n")
    assert "host,data,string,192.168.20.148" in text
    assert "port,data,u16,8443" in text
    redacted = redact_csv_for_display(text)
    assert "tttttttt" not in redacted
    assert "redacted" in redacted


def test_ca_pem_requires_file_row(tmp_path: Path) -> None:
    boot = _boot(coordinator_ca_pem="-----BEGIN CERTIFICATE-----\nX\n-----END CERTIFICATE-----")
    with pytest.raises(NvsProvisionError, match="ca_pem_path"):
        personal_pending_nvs_rows(boot)
    ca = tmp_path / "ca.pem"
    ca.write_text(boot.coordinator_ca_pem + "\n", encoding="utf-8")
    rows = personal_pending_nvs_rows(boot, ca_pem_path=ca)
    assert rows[-1].key == "ca_pem" and rows[-1].type == "file"


def test_write_artifacts_csv_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IDF_PATH", raising=False)
    out = tmp_path / "prov"
    art = write_personal_pending_nvs_provision(_boot(), out, generate_bin=True)
    assert art.csv_path.is_file()
    assert art.bin_path is None  # 無 IDF_PATH
    assert art.readme_path.is_file()
    assert "未燒錄" in art.readme_path.read_text(encoding="utf-8")
    assert art.public_summary["flashed"] is False


def test_cli_rejects_flash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STACKCHAN_COORDINATOR_URL", "http://192.168.20.148:8443")
    monkeypatch.setenv("STACKCHAN_DEVICE_ID", "cores3_primary")
    monkeypatch.setenv("STACKCHAN_DEVICE_TOKEN", "u" * 40)
    assert device_main(["provision-nvs", "--out-dir", str(tmp_path / "x"), "--flash"]) == 1


def test_cli_provision_nvs_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("STACKCHAN_COORDINATOR_URL", "http://192.168.20.148:8443")
    monkeypatch.setenv("STACKCHAN_DEVICE_ID", "cores3_primary")
    monkeypatch.setenv("STACKCHAN_DEVICE_TOKEN", "v" * 40)
    monkeypatch.delenv("IDF_PATH", raising=False)
    out = tmp_path / "nvs_out"
    assert device_main(["provision-nvs", "--out-dir", str(out), "--no-bin"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["flashed"] is False
    assert payload["efuse_written"] is False
    assert Path(payload["csv"]).is_file()
    csv_text = Path(payload["csv"]).read_text(encoding="utf-8")
    assert "personal_pend,namespace" in csv_text
    assert "vvvv" in csv_text  # 檔案內有 token；勿提交
