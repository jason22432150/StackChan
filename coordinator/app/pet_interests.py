"""五類興趣系統骨架（Phase 0：常數與夾值工具）。"""

from __future__ import annotations

INTEREST_IDS = ("reading", "coding", "food", "exploration", "creative")
INTEREST_LABELS_ZH = {
    "reading": "閱讀",
    "coding": "研究與工作",
    "food": "美食",
    "exploration": "探索",
    "creative": "藝術與創作",
}


def clamp_score(score: int) -> int:
    return max(0, min(100, int(score)))


def default_interests(initial: int = 50) -> dict[str, int]:
    value = clamp_score(initial)
    return {interest_id: value for interest_id in INTEREST_IDS}
