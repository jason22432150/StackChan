"""P2-09：規格與原始碼必須維持 A0，不得宣稱已完成 TTS／短提示音。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY_H = ROOT / "firmware/main/stackchan/notifications/notification_audio_policy.h"
CHECKLIST = ROOT / "docs/stackchan-agent-spec/docs/09_DEVELOPMENT_CHECKLIST.md"


def test_mvp_capability_macro_is_a0() -> None:
    text = POLICY_H.read_text(encoding="utf-8")
    assert "kMvpAgentAudioCapability = AgentAudioCapability::A0" in text
    # 不得引入原廠播放／Codec 標頭（註解可提及 PlaySound 作為禁止項說明）。
    assert '#include "application.h"' not in text.lower()
    assert "audio_codec" not in text.lower()
    assert '#include "' not in text or "resource_arbiter.h" in text


def test_checklist_p209_does_not_claim_tts_without_a0_gate() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    assert "**P2-09**" in text
    # 完成勾選時必須出現 A0 Evidence；本測試在 commit 後才會綠。
    line = next(line for line in text.splitlines() if "**P2-09**" in line)
    if line.startswith("- [x]"):
        assert "A0" in line
        assert "不宣稱" in line or "未驗證" in line or "純 UI" in line
