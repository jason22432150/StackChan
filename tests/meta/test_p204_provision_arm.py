"""P2-04：憑證／provision → arm 產品 stream 的 Fail-Closed 掛點。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION_H = ROOT / "firmware/main/stackchan/notifications/stream_session_start.h"
BOOTSTRAP_H = ROOT / "firmware/main/stackchan/notifications/stream_bootstrap.h"
RUNTIME_H = ROOT / "firmware/main/stackchan/notifications/notification_product_runtime.h"
RUNTIME_CPP = ROOT / "firmware/main/stackchan/notifications/notification_product_runtime.cpp"
CHECKLIST = ROOT / "docs/stackchan-agent-spec/docs/09_DEVELOPMENT_CHECKLIST.md"
FIRMWARE = ROOT / "docs/stackchan-agent-spec/docs/04_FIRMWARE_XIAOZHI.md"


def test_arm_api_exists() -> None:
    text = SESSION_H.read_text(encoding="utf-8")
    assert "armProvisionedDeviceStream" in text
    assert "armProvisionedDeviceStreamLinked" in text


def test_fetch_and_arm_api_exists() -> None:
    text = BOOTSTRAP_H.read_text(encoding="utf-8")
    assert "fetchAndArmDeviceStream" in text


def test_runtime_arm_does_not_auto_fetch() -> None:
    header = RUNTIME_H.read_text(encoding="utf-8")
    body = RUNTIME_CPP.read_text(encoding="utf-8")
    assert "armNotificationProductRuntime" in header
    assert "isNotificationProductStreamArmed" in header
    assert "fetchAndArmDeviceStream" not in body
    assert "fetchAndProvisionDeviceStream" not in body
    assert "armProvisionedDeviceStream" in body


def test_checklist_p204_p208_remain_unchecked() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    for key in ("**P2-04**", "**P2-08**"):
        line = next(line for line in text.splitlines() if key in line)
        assert line.startswith("- [ ]"), f"{key} 不得在 Gate 未完成時勾選"


def test_firmware_doc_mentions_arm() -> None:
    text = FIRMWARE.read_text(encoding="utf-8")
    assert "armProvisionedDeviceStream" in text or "fetchAndArmDeviceStream" in text
