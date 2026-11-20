"""雲端 LLM Provider 最小介面（Phase 0：僅定義契約，不呼叫真實 API）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# 寵物高階活動白名單；模型不可輸出任意馬達角度或系統指令
ALLOWED_PET_ACTIONS = frozenset(
    {
        "idle",
        "sleep",
        "read",
        "work",
        "eat",
        "walk",
        "look_around",
        "celebrate",
        "explore",
        "create",
    }
)


@dataclass(slots=True)
class ReplyResult:
    text: str
    provider: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PetActionProposal:
    action: str
    emotion: str = "neutral"
    duration_s: int = 60
    optional_short_line: str | None = None
    reason_code: str = "mock"


class LlmProvider(ABC):
    """至少兩個真實 Provider 的共同介面；Phase 0 使用 mock 實作。"""

    name: str

    @abstractmethod
    async def generate_reply(self, context: dict[str, Any], user_text: str) -> ReplyResult:
        """依使用者文字產生回覆（Phase 0 mock 不連外）。"""

    @abstractmethod
    async def choose_pet_action(self, context: dict[str, Any]) -> PetActionProposal:
        """選擇下一個高階寵物活動；回傳必須落在白名單。"""
