"""R-006 實機量測 probe：存在進入點；未取得序列 R006_MEASURE 前不得關閉風險。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE_H = ROOT / "firmware/main/stackchan/notifications/fail_closed_revoke_probe.h"
KCONFIG = ROOT / "firmware/main/Kconfig.projbuild"
RISKS = ROOT / "docs/stackchan-agent-spec/docs/08_RISKS_AND_UNKNOWNS.md"
EVIDENCE = ROOT / "docs/stackchan-agent-spec/docs/evidence"


def test_probe_api_and_kconfig_exist() -> None:
    text = PROBE_H.read_text(encoding="utf-8")
    assert "FailClosedRevokeProbe" in text
    assert "FailClosedRevokeSample" in text
    kconfig = KCONFIG.read_text(encoding="utf-8")
    assert "STACKCHAN_R006_REVOKE_PROBE" in kconfig
    assert "default n" in kconfig


def test_r006_close_requires_device_measure_evidence() -> None:
    risks = RISKS.read_text(encoding="utf-8")
    line = next(line for line in risks.splitlines() if "| R-006 |" in line)
    if "已關閉" in line or "CLOSED" in line.replace("Fail-Closed", ""):
        # 關閉時必須有實機序列證據檔
        matches = list(EVIDENCE.glob("r006*.md")) + list(EVIDENCE.glob("R006*"))
        assert matches, "關閉 R-006 需要 docs/.../evidence 實機紀錄"
        assert "revoke_ms" in matches[0].read_text(encoding="utf-8")
