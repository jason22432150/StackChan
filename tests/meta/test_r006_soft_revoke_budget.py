"""R-006：軟體失聯撤銷預算公式與風險登錄一致。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUDGET_H = ROOT / "firmware/main/stackchan/notifications/fail_closed_budget.h"
RISKS = ROOT / "docs/stackchan-agent-spec/docs/08_RISKS_AND_UNKNOWNS.md"
CHECKLIST = ROOT / "docs/stackchan-agent-spec/docs/09_DEVELOPMENT_CHECKLIST.md"
EVIDENCE = ROOT / "docs/stackchan-agent-spec/docs/evidence"


def test_firmware_defines_soft_budget_formula() -> None:
    text = BUDGET_H.read_text(encoding="utf-8")
    assert "kP004MaxUiUpdateGapMs = 185" in text
    assert "kMvpSoftWorstCaseRevokeMs" in text
    assert "mvpSoftWorstCaseRevokeMs" in text


def test_r006_risk_line_has_budget_and_device_or_open() -> None:
    risks = RISKS.read_text(encoding="utf-8")
    line = next(line for line in risks.splitlines() if "| R-006 |" in line)
    assert "4185" in line
    if "已關閉" in line:
        evidence = (EVIDENCE / "r006_device_revoke_measure.md").read_text(encoding="utf-8")
        assert "revoke_ms=4000" in evidence or "revoke_ms" in evidence


def test_checklist_p204_p208_remain_unchecked() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    for key in ("**P2-04**", "**P2-08**"):
        line = next(line for line in text.splitlines() if key in line)
        assert line.startswith("- [ ]"), f"{key} 不得在 Gate 未完成時勾選"
