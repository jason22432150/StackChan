from __future__ import annotations

import json

import pytest

from firmware.verify_nvs_efuse import check_hmac_slot, main


def summary(key_id: int, purpose: str = "HMAC_UP") -> dict:
    values = {
        f"KEY_PURPOSE_{key_id}": purpose,
        "RD_DIS": 1 << key_id,
        "WR_DIS": 1 << (23 + key_id),
    }
    return {name: {"name": name, "readable": True, "value": value} for name, value in values.items()}


@pytest.mark.parametrize("key_id", range(6))
def test_checks_selected_slot_only(key_id):
    report = summary(key_id)
    assert check_hmac_slot(report, key_id) == ()
    neighbor = (key_id + 1) % 6
    report["RD_DIS"]["value"] = 1 << neighbor
    report["WR_DIS"]["value"] = 1 << (23 + neighbor)
    assert check_hmac_slot(report, key_id) == (
        "key block must be read-protected",
        "key block must be write-protected",
    )


def test_rejects_wrong_purpose_and_unfiltered_reports():
    report = summary(0, "XTS_AES_128_KEY")
    assert check_hmac_slot(report, 0) == ("key purpose must be HMAC_UP",)
    with pytest.raises(ValueError, match="filtered"):
        check_hmac_slot(report, 1)
    report["BLOCK_KEY0"] = {"value": "excluded"}
    with pytest.raises(ValueError, match="filtered"):
        check_hmac_slot(report, 0)


@pytest.mark.parametrize("value", [True, -1, 128, "1"])
def test_rejects_invalid_read_masks(value):
    report = summary(0)
    report["RD_DIS"]["value"] = value
    with pytest.raises(ValueError, match="invalid eFuse protection mask"):
        check_hmac_slot(report, 0)


def test_rejects_unreadable_metadata_or_invalid_slot():
    report = summary(0)
    report["KEY_PURPOSE_0"]["readable"] = False
    with pytest.raises(ValueError, match="unreadable"):
        check_hmac_slot(report, 0)
    with pytest.raises(ValueError, match="between 0 and 5"):
        check_hmac_slot(report, 6)


def test_cli_exit_status_and_no_report_values(tmp_path, capsys):
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(summary(5)), encoding="utf-8")
    args = [str(path), "--key-id", "5"]
    assert main(args) == 0
    assert "HMAC_UP, read-protected, write-protected" in capsys.readouterr().out
    path.write_text(json.dumps(summary(5, "untrusted-report-value")), encoding="utf-8")
    assert main(args) == 1
    output = capsys.readouterr().out
    assert "key purpose must be HMAC_UP" in output
    assert "untrusted-report-value" not in output
    path.write_text('{"RD_DIS": {}, "RD_DIS": {}}', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
    assert "duplicate fields" in capsys.readouterr().err
