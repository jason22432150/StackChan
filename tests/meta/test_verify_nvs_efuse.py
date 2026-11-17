from __future__ import annotations

import json

import pytest

from firmware.verify_nvs_efuse import check_hmac_slot, key_id_from_sdkconfig, main


SDKCONFIG = (
    'CONFIG_IDF_TARGET="esp32s3"\n'
    "CONFIG_NVS_ENCRYPTION=y\n"
    "CONFIG_NVS_SEC_KEY_PROTECT_USING_HMAC=y\n"
    "# CONFIG_NVS_SEC_KEY_PROTECT_NONE is not set\n"
    "CONFIG_NVS_SEC_HMAC_EFUSE_KEY_ID=5\n"
)


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


@pytest.mark.parametrize(
    ("config", "error"),
    [
        (SDKCONFIG.replace('"esp32s3"', '"esp32"'), "must target ESP32-S3"),
        (SDKCONFIG.replace("CONFIG_NVS_ENCRYPTION=y", "# CONFIG_NVS_ENCRYPTION is not set"), "enable HMAC"),
        (SDKCONFIG.replace("CONFIG_NVS_SEC_KEY_PROTECT_USING_HMAC=y\n", ""), "enable HMAC"),
        (SDKCONFIG + "CONFIG_NVS_SEC_KEY_PROTECT_USING_FLASH_ENC=y\n", "enable HMAC"),
        (SDKCONFIG.replace("KEY_ID=5", "KEY_ID=-1"), "key ID between"),
        (SDKCONFIG.replace("KEY_ID=5", "KEY_ID=6"), "key ID between"),
        (SDKCONFIG.replace("CONFIG_NVS_SEC_HMAC_EFUSE_KEY_ID=5\n", ""), "key ID between"),
        (SDKCONFIG + "CONFIG_NVS_SEC_HMAC_EFUSE_KEY_ID=1\n", "duplicate"),
        (SDKCONFIG + "# CONFIG_NVS_ENCRYPTION is not set\n", "duplicate"),
    ],
)
def test_sdkconfig_rejects_ambiguous_or_incompatible_settings(tmp_path, config, error):
    path = tmp_path / "sdkconfig"
    path.write_text(config, encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        key_id_from_sdkconfig(path)


def test_cli_sdkconfig_checks_only_the_configured_slot(tmp_path, capsys):
    config = tmp_path / "sdkconfig"
    config.write_text(SDKCONFIG, encoding="utf-8")
    path = tmp_path / "summary.json"
    args = [str(path), "--sdkconfig", str(config)]
    path.write_text(json.dumps(summary(5)), encoding="utf-8")
    assert main(args) == 0
    assert "key ID 5" in capsys.readouterr().out
    path.write_text(json.dumps(summary(0)), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
    assert "filtered to the selected purpose" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        main([*args, "--key-id", "0"])
    assert exc.value.code == 2
