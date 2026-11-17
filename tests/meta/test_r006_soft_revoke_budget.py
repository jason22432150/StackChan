"""R-006：軟體失聯撤銷預算已設計並對齊；不得宣稱實機量測完成。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUDGET_H = ROOT / "firmware/main/stackchan/notifications/fail_closed_budget.h"
RISKS = ROOT / "docs/stackchan-agent-spec/docs/08_RISKS_AND_UNKNOWNS.md"
CHECKLIST = ROOT / "docs/stackchan-agent-spec/docs/09_DEVELOPMENT_CHECKLIST.md"


def test_firmware_defines_soft_budget_formula() -> None:
    text = BUDGET_H.read_text(encoding="utf-8")
    assert "kP004MaxUiUpdateGapMs = 185" in text
    assert "kMvpSoftWorstCaseRevokeMs" in text
    assert "mvpSoftWorstCaseRevokeMs" in text
    assert "非實機量測" in text or "不是實機" in text or "非實機" in text


def test_r006_remains_open_until_device_measurement() -> None:
    risks = RISKS.read_text(encoding="utf-8")
    line = next(line for line in risks.splitlines() if "| R-006 |" in line)
    assert "4185" in line or "軟" in line
    assert "實機" in line or "未量測" in line or "燒錄" in line
    # 不得偽裝成風險已關閉（勿誤判「Fail-Closed」字樣）
    assert "已關閉" not in line
    assert "風險關閉" not in line
    assert "CLOSED" not in line.replace("Fail-Closed", "").upper()


def test_checklist_does_not_check_p204_or_p208_without_r006_device() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    for key in ("**P2-04**", "**P2-08**"):
        line = next(line for line in text.splitlines() if key in line)
        if line.startswith("- [x]"):
            assert "R-006" in line
            assert "未" in line  # 未燒錄／未量測
