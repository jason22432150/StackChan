"""P2-04：NotificationProductLoop 產品主迴圈掛點與清單紀律。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOOP_H = ROOT / "firmware/main/stackchan/notifications/notification_product_loop.h"
RUNTIME_H = ROOT / "firmware/main/stackchan/notifications/notification_product_runtime.h"
HAL = ROOT / "firmware/main/hal/hal.cpp"
KCONFIG = ROOT / "firmware/main/Kconfig.projbuild"
CHECKLIST = ROOT / "docs/stackchan-agent-spec/docs/09_DEVELOPMENT_CHECKLIST.md"
FIRMWARE = ROOT / "docs/stackchan-agent-spec/docs/04_FIRMWARE_XIAOZHI.md"


def test_product_loop_api_exists() -> None:
    text = LOOP_H.read_text(encoding="utf-8")
    assert "class NotificationProductLoop" in text
    assert "notificationProductLoopPollClient" in text
    assert "notificationProductLoopLinked" in text


def test_kconfig_default_disabled() -> None:
    text = KCONFIG.read_text(encoding="utf-8")
    assert "config STACKCHAN_AGENT_NOTIFICATIONS" in text
    # default n 必須緊跟 config，避免誤開 TLS／主迴圈
    block = text.split("config STACKCHAN_AGENT_NOTIFICATIONS", 1)[1]
    assert "default n" in block.split("\n", 8)[0:8] or "\n    default n\n" in block[:200]


def test_hal_publishes_activity_and_worker_owns_stream() -> None:
    text = HAL.read_text(encoding="utf-8")
    task = (ROOT / "firmware/main/stackchan/notifications/notification_product_task.cpp").read_text(
        encoding="utf-8"
    )
    assert "CONFIG_STACKCHAN_AGENT_NOTIFICATIONS" in text
    assert "publishNotificationXiaozhiBusy" in text
    assert "tickNotificationProductRuntime" not in text
    assert "fetchAndArmNotificationProductRuntime" not in text
    assert "tickNotificationProductRuntime" in task
    assert "fetchAndArmNotificationProductRuntime" in task


def test_runtime_does_not_auto_start_tls() -> None:
    runtime = (ROOT / "firmware/main/stackchan/notifications/notification_product_runtime.cpp").read_text(
        encoding="utf-8"
    )
    assert "initNotificationProductRuntime" in runtime
    assert "startProvisionedDeviceStream" not in runtime
    assert "client.start(" not in runtime
    for function in ("initNotificationProductRuntime", "tickNotificationProductRuntime"):
        body = runtime.split(f"void {function}(", 1)[1].split("\n}", 1)[0]
        assert "fetchAndArm" not in body
        assert "loadNotificationCredentials" not in body


def test_checklist_p204_p208_remain_unchecked() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    for key in ("**P2-04**", "**P2-08**"):
        line = next(line for line in text.splitlines() if key in line)
        assert line.startswith("- [ ]"), f"{key} 不得在 Gate 未完成時勾選"


def test_firmware_doc_mentions_product_loop() -> None:
    text = FIRMWARE.read_text(encoding="utf-8")
    assert "NotificationProductLoop" in text or "STACKCHAN_AGENT_NOTIFICATIONS" in text
