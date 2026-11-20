"""Phase 0 mock Providers：無金鑰、不連外、固定可測行為。"""

from __future__ import annotations

from typing import Any

from .base import ALLOWED_PET_ACTIONS, LlmProvider, PetActionProposal, ReplyResult


class MockProviderA(LlmProvider):
    name = "provider_a"

    async def generate_reply(self, context: dict[str, Any], user_text: str) -> ReplyResult:
        _ = context
        return ReplyResult(
            text=f"[mock-A] 收到：{user_text}",
            provider=self.name,
            meta={"mock": True},
        )

    async def choose_pet_action(self, context: dict[str, Any]) -> PetActionProposal:
        energy = int(context.get("energy", 70))
        action = "sleep" if energy < 30 else "read"
        assert action in ALLOWED_PET_ACTIONS
        return PetActionProposal(
            action=action,
            emotion="calm" if action == "sleep" else "curious",
            duration_s=120,
            optional_short_line="我先安靜一下。" if action == "sleep" else "我來看書。",
            reason_code="mock_a",
        )


class MockProviderB(LlmProvider):
    name = "provider_b"

    async def generate_reply(self, context: dict[str, Any], user_text: str) -> ReplyResult:
        _ = context
        return ReplyResult(
            text=f"[mock-B] 了解：{user_text}",
            provider=self.name,
            meta={"mock": True},
        )

    async def choose_pet_action(self, context: dict[str, Any]) -> PetActionProposal:
        _ = context
        action = "walk"
        assert action in ALLOWED_PET_ACTIONS
        return PetActionProposal(
            action=action,
            emotion="happy",
            duration_s=90,
            optional_short_line="我走走看。",
            reason_code="mock_b",
        )


def get_provider(name: str) -> LlmProvider:
    """依設定名稱取得 Provider；未知名稱時明確失敗。"""
    providers: dict[str, LlmProvider] = {
        MockProviderA.name: MockProviderA(),
        MockProviderB.name: MockProviderB(),
    }
    if name not in providers:
        raise KeyError(f"未知 LLM provider: {name}")
    return providers[name]
