"""個人版：AgentEvent → NotificationIntent（FIFO／優先／TTL 素材）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from stackchan.contracts import validate_notification_intent

# 個人版預設：UI＋輕量 Motion；音訊／TTS 仍關閉（A0）。
_PERSONAL_PRESENTATION = {
    "ui": True,
    "audio": False,
    "motion": True,
    "tts": False,
}

# 事件類型 → 優先級（0..100）；越高越先被優先通道考慮。
_PRIORITY_BY_TYPE: dict[str, int] = {
    "task.failed": 80,
    "response.completed": 60,
    "task.started": 40,
    "task.waiting": 35,
}


def priority_for_event_type(event_type: str) -> int:
    """依事件類型決定佇列優先級（不推導 task.succeeded）。"""
    return _PRIORITY_BY_TYPE.get(event_type, 30)


def build_personal_notification_intent(
    event: dict[str, Any],
    *,
    device_id: str,
    # 與裝置 boot 預設 pol_personal_v1 對齊，避免 receiveItem 拒收
    policy_version: str = "pol_personal_v1",
    generation: int = 1,
    ttl_seconds: int = 600,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    由已驗證 AgentEvent 建立契約合法的 NotificationIntent。

    - response.completed 只當 observed 通知，不宣稱任務成功
    - presentation 不含 TTS／音訊
    """
    if not device_id.strip():
        raise ValueError("device_id 不可為空")
    if ttl_seconds < 30 or ttl_seconds > 86_400:
        raise ValueError("ttl_seconds 必須在 30..86400")
    if generation < 0:
        raise ValueError("generation 不可為負")

    event_id = str(event["event_id"])
    event_type = str(event["event_type"])
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    expires = clock.astimezone(timezone.utc) + timedelta(seconds=ttl_seconds)
    expires_at = expires.strftime("%Y-%m-%dT%H:%M:%SZ")

    # delivery_id 與 event 綁定，重送同一 event_id 時可去重。
    delivery_id = f"dlv_{event_id}"
    notification_id = f"ntf_{event_id}"
    if len(delivery_id) > 128:
        delivery_id = delivery_id[:128]
    if len(notification_id) > 128:
        notification_id = notification_id[:128]

    intent = {
        "schema_version": "0.1",
        "notification_id": notification_id,
        "delivery_id": delivery_id,
        "device_id": device_id,
        "event_ids": [event_id],
        "priority": priority_for_event_type(event_type),
        "policy_version": policy_version,
        "generation": generation,
        "expires_at": expires_at,
        "presentation_policy": dict(_PERSONAL_PRESENTATION),
        "presentation_profile": "personal.basic_notice",
    }
    return validate_notification_intent(intent)
