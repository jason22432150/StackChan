"""Adapter 登錄：僅允許受授權來源。"""

from __future__ import annotations

import pytest

from stackchan.adapters import AdapterError, get_adapter


def test_authorized_aliases() -> None:
    assert get_adapter("codex").capability.adapter_id == "codex.hooks"
    assert get_adapter("cursor.hooks").capability.adapter_id == "cursor.hooks"


def test_unauthorized_adapter_rejected() -> None:
    with pytest.raises(AdapterError, match="未授權"):
        get_adapter("chatgpt.ui-scrape")
