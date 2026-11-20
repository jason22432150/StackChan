"""SQLite 初始化與主動發言 Gate 測試。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.device_ws import DeviceWsHub
from app.pet_interests import default_interests
from app.proactivity import ProactivityGate
from app.storage import Storage


def test_storage_initializes_interests(tmp_path):
    db = tmp_path / "t.db"
    storage = Storage(db)
    try:
        assert storage.get_schema_version() == 1
        interests = storage.list_interests()
        assert set(interests) == {"reading", "coding", "food", "exploration", "creative"}
        assert all(score == 50 for score in interests.values())
    finally:
        storage.close()


def test_default_interests_helper():
    assert default_interests()["reading"] == 50


def test_proactivity_rejects_outside_companion():
    gate = ProactivityGate()
    decision = gate.allow_voice(
        device_mode="factory_ai",
        companion_active=False,
        user_dialogue_active=False,
        speaking=False,
    )
    assert decision.allowed is False
    assert decision.reason == "not_companion"


def test_proactivity_rejects_quiet_hours():
    gate = ProactivityGate(quiet_start="23:00", quiet_end="08:00", timezone="Asia/Taipei")
    night = datetime(2026, 11, 20, 23, 30, tzinfo=ZoneInfo("Asia/Taipei"))
    decision = gate.allow_voice(
        device_mode="companion",
        companion_active=True,
        user_dialogue_active=False,
        speaking=False,
        now=night,
    )
    assert decision.allowed is False
    assert decision.reason == "quiet_hours"


def test_proactivity_allows_daytime_companion():
    gate = ProactivityGate(timezone="Asia/Taipei")
    day = datetime(2026, 11, 20, 15, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    decision = gate.allow_voice(
        device_mode="companion",
        companion_active=True,
        user_dialogue_active=False,
        speaking=False,
        now=day,
    )
    assert decision.allowed is True


def test_device_hub_mode_isolation():
    hub = DeviceWsHub()
    assert hub.can_push_companion_ui() is False
    hub.set_mode("companion", active=True)
    # Phase 1：尚需有效 session／websocket 才允許推送
    assert hub.can_push_companion_ui() is False
    hub.session.session_id = "sess-test"
    hub.session.websocket = object()  # type: ignore[assignment]
    assert hub.can_push_companion_ui() is True
    hub.set_mode("launcher", active=False)
    assert hub.can_push_companion_ui() is False
