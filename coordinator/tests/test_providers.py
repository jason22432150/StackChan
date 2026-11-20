"""Mock Provider 介面測試。"""

from __future__ import annotations

import pytest

from app.providers import get_provider
from app.providers.base import ALLOWED_PET_ACTIONS


@pytest.mark.asyncio
async def test_provider_a_reply_and_action():
    provider = get_provider("provider_a")
    reply = await provider.generate_reply({}, "你好")
    assert "mock-A" in reply.text
    action = await provider.choose_pet_action({"energy": 10})
    assert action.action in ALLOWED_PET_ACTIONS
    assert action.action == "sleep"


@pytest.mark.asyncio
async def test_provider_b_reply_and_action():
    provider = get_provider("provider_b")
    reply = await provider.generate_reply({}, "測試")
    assert "mock-B" in reply.text
    action = await provider.choose_pet_action({})
    assert action.action == "walk"


def test_unknown_provider_raises():
    with pytest.raises(KeyError):
        get_provider("does_not_exist")


def test_active_provider_ping(client):
    response = client.get("/api/providers/active/ping")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "provider_a"
    assert body["pet_action"] in ALLOWED_PET_ACTIONS
