"""Companion 控制協定 v1 解析與驗證（Phase 1）。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 1
MAX_TEXT_CHARS = 160
MAX_QUEUE = 32

ALLOWED_ANIMATIONS = frozenset(
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
        "reading",  # 協定示例別名，對應 read
    }
)

ALLOWED_EXPRESSIONS = frozenset(
    {
        "neutral",
        "happy",
        "angry",
        "sad",
        "doubt",
        "sleepy",
        "curious",
        "calm",
        "thinking",
    }
)

ALLOWED_STATES = frozenset(
    {"IDLE", "LISTENING", "THINKING", "SPEAKING", "NOTIFYING", "OFFLINE"}
)

# 裝置端會再次限位；此處先擋明顯越界
MOTION_YAW_DEG_LIMIT = (-45.0, 45.0)
MOTION_PITCH_DEG_LIMIT = (-20.0, 30.0)
MOTION_SPEED_LIMIT = (50, 400)

# Companion 活動連線才可下發的 UI／動作指令
PUSH_TYPES = frozenset(
    {
        "text.show",
        "expression.set",
        "motion.set",
        "animation.play",
        "state.set",
        "pet.state",
        "pet.activity",
        "pet.proactive",
        "stop",
        "hello.ok",
        "heartbeat",
        "ack",
    }
)

DEVICE_INBOUND_TYPES = frozenset(
    {
        "hello",
        "heartbeat",
        "ack",
        "stop",
        "interaction.touch",
        "device.mode",
        "dialogue.cancel",
        "playback.done",
        "pet.activity.completed",
        "wake.detected",
    }
)


@dataclass(slots=True)
class Envelope:
    v: int
    id: str
    type: str
    payload: dict[str, Any]
    ts_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "v": self.v,
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
        }
        if self.ts_ms is not None:
            data["ts_ms"] = self.ts_ms
        return data


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def new_id(prefix: str = "msg") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def now_ms() -> int:
    return int(time.time() * 1000)


def make_envelope(msg_type: str, payload: dict[str, Any] | None = None, *, msg_id: str | None = None) -> Envelope:
    return Envelope(
        v=PROTOCOL_VERSION,
        id=msg_id or new_id(),
        type=msg_type,
        payload=payload or {},
        ts_ms=now_ms(),
    )


def parse_envelope(raw: Any) -> Envelope:
    if not isinstance(raw, dict):
        raise ProtocolError("invalid_json", "訊息必須為 JSON object")
    if raw.get("v") != PROTOCOL_VERSION:
        raise ProtocolError("bad_version", f"不支援的協定版本: {raw.get('v')}")
    msg_id = raw.get("id")
    msg_type = raw.get("type")
    payload = raw.get("payload")
    if not isinstance(msg_id, str) or not msg_id or len(msg_id) > 64:
        raise ProtocolError("bad_id", "id 必須為非空字串且 ≤64")
    if not isinstance(msg_type, str) or not msg_type or len(msg_type) > 64:
        raise ProtocolError("bad_type", "type 無效")
    if not isinstance(payload, dict):
        raise ProtocolError("bad_payload", "payload 必須為 object")
    ts_ms = raw.get("ts_ms")
    if ts_ms is not None and not isinstance(ts_ms, int):
        raise ProtocolError("bad_ts", "ts_ms 必須為整數")
    return Envelope(v=PROTOCOL_VERSION, id=msg_id, type=msg_type, payload=payload, ts_ms=ts_ms)


def validate_device_inbound(envelope: Envelope) -> None:
    if envelope.type not in DEVICE_INBOUND_TYPES:
        raise ProtocolError("unknown_type", f"未知裝置訊息: {envelope.type}")
    if envelope.type == "hello":
        device_id = envelope.payload.get("device_id")
        mode = envelope.payload.get("mode", "companion")
        if not isinstance(device_id, str) or not device_id or len(device_id) > 64:
            raise ProtocolError("bad_hello", "hello.device_id 無效")
        if mode not in {"companion", "launcher", "factory_ai"}:
            raise ProtocolError("bad_hello", "hello.mode 無效")
    if envelope.type == "device.mode":
        mode = envelope.payload.get("mode")
        active = envelope.payload.get("active")
        if mode not in {"companion", "launcher", "factory_ai"}:
            raise ProtocolError("bad_mode", "device.mode.mode 無效")
        if not isinstance(active, bool):
            raise ProtocolError("bad_mode", "device.mode.active 必須為 bool")


def validate_push_command(envelope: Envelope, *, max_text_chars: int = MAX_TEXT_CHARS) -> None:
    if envelope.type not in PUSH_TYPES:
        raise ProtocolError("unknown_type", f"未知下發訊息: {envelope.type}")

    p = envelope.payload
    if envelope.type == "text.show":
        text = p.get("text", "")
        if not isinstance(text, str) or len(text) > max_text_chars:
            raise ProtocolError("text_too_long", f"文字超過 {max_text_chars} 字元")
    elif envelope.type == "expression.set":
        name = p.get("name")
        if name not in ALLOWED_EXPRESSIONS:
            raise ProtocolError("bad_expression", f"表情不在白名單: {name}")
    elif envelope.type == "animation.play":
        name = p.get("name")
        if name not in ALLOWED_ANIMATIONS:
            raise ProtocolError("bad_animation", f"動畫不在白名單: {name}")
    elif envelope.type == "motion.set":
        yaw = p.get("yaw_deg", 0)
        pitch = p.get("pitch_deg", 0)
        speed = p.get("speed", 200)
        if not isinstance(yaw, (int, float)) or not isinstance(pitch, (int, float)):
            raise ProtocolError("bad_motion", "yaw/pitch 必須為數字")
        if not isinstance(speed, (int, float)):
            raise ProtocolError("bad_motion", "speed 必須為數字")
        if not (MOTION_YAW_DEG_LIMIT[0] <= float(yaw) <= MOTION_YAW_DEG_LIMIT[1]):
            raise ProtocolError("motion_yaw_limit", "yaw 超出安全範圍")
        if not (MOTION_PITCH_DEG_LIMIT[0] <= float(pitch) <= MOTION_PITCH_DEG_LIMIT[1]):
            raise ProtocolError("motion_pitch_limit", "pitch 超出安全範圍")
        if not (MOTION_SPEED_LIMIT[0] <= int(speed) <= MOTION_SPEED_LIMIT[1]):
            raise ProtocolError("motion_speed_limit", "speed 超出安全範圍")
    elif envelope.type == "state.set":
        state = p.get("state")
        if state not in ALLOWED_STATES:
            raise ProtocolError("bad_state", f"狀態無效: {state}")
    elif envelope.type == "pet.activity":
        action = p.get("action")
        if action not in ALLOWED_ANIMATIONS and action not in {"idle", "sleep", "read", "work", "eat", "walk"}:
            raise ProtocolError("bad_activity", f"活動不在白名單: {action}")
