"""裝置 WebSocket Hub：hello／heartbeat／ack、模式隔離、指令下發（Phase 1）。"""

from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.protocol import (
    Envelope,
    ProtocolError,
    make_envelope,
    parse_envelope,
    validate_device_inbound,
    validate_push_command,
)

logger = logging.getLogger(__name__)


@dataclass
class DeviceSession:
    device_id: str | None = None
    session_id: str | None = None
    mode: str = "offline"
    active: bool = False
    last_heartbeat_ms: int | None = None
    websocket: WebSocket | None = None


@dataclass
class DeviceWsHub:
    """單一裝置 Companion 連線（個人版；同時只服務一個活動 session）。"""

    expected_token: str = ""
    protocol_version: int = 1
    max_text_chars: int = 160
    session: DeviceSession = field(default_factory=DeviceSession)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def set_mode(self, mode: str, *, active: bool) -> None:
        self.session.mode = mode
        self.session.active = active

    def can_push_companion_ui(self) -> bool:
        return (
            self.session.active
            and self.session.mode == "companion"
            and self.session.websocket is not None
            and self.session.session_id is not None
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "device_id": self.session.device_id,
            "session_id": self.session.session_id,
            "mode": self.session.mode,
            "active": self.session.active,
            "can_push": self.can_push_companion_ui(),
            "last_heartbeat_ms": self.session.last_heartbeat_ms,
        }

    async def handle_socket(self, websocket: WebSocket, *, token: str | None) -> None:
        if not self._authorize(token):
            await websocket.close(code=4401)
            return

        await websocket.accept()
        try:
            while True:
                raw = await websocket.receive_json()
                try:
                    envelope = parse_envelope(raw)
                    validate_device_inbound(envelope)
                except ProtocolError as exc:
                    await self._send(
                        websocket,
                        make_envelope(
                            "ack",
                            {"ok": False, "reply_to": raw.get("id") if isinstance(raw, dict) else None, "error": exc.code},
                        ),
                    )
                    continue
                await self._dispatch_inbound(websocket, envelope)
        except WebSocketDisconnect:
            logger.info("device websocket disconnected")
        finally:
            await self._clear_if_current(websocket)

    def _authorize(self, token: str | None) -> bool:
        # 未設定 expected_token 時僅供本機開發；正式 Pi 應設定 token
        if not self.expected_token:
            return True
        if not token:
            return False
        return secrets.compare_digest(token, self.expected_token)

    async def _dispatch_inbound(self, websocket: WebSocket, envelope: Envelope) -> None:
        if envelope.type == "hello":
            async with self._lock:
                # 新連線取代舊連線（個人裝置）
                old = self.session.websocket
                self.session.device_id = str(envelope.payload["device_id"])
                self.session.session_id = secrets.token_hex(8)
                self.session.mode = str(envelope.payload.get("mode", "companion"))
                self.session.active = True
                self.session.websocket = websocket
            if old is not None and old is not websocket:
                try:
                    await old.close(code=4000)
                except Exception:  # noqa: BLE001 — 舊連線關閉失敗可忽略
                    pass
            await self._send(
                websocket,
                make_envelope(
                    "hello.ok",
                    {
                        "session_id": self.session.session_id,
                        "protocol_version": self.protocol_version,
                        "settings": {"max_text_chars": self.max_text_chars},
                    },
                    msg_id=f"ack-{envelope.id}",
                ),
            )
            return

        if envelope.type == "device.mode":
            self.set_mode(str(envelope.payload["mode"]), active=bool(envelope.payload["active"]))
            await self._send(
                websocket,
                make_envelope("ack", {"ok": True, "reply_to": envelope.id}),
            )
            return

        if envelope.type == "heartbeat":
            self.session.last_heartbeat_ms = envelope.ts_ms
            await self._send(
                websocket,
                make_envelope(
                    "heartbeat",
                    {"uptime_ms": envelope.payload.get("uptime_ms", 0), "state": envelope.payload.get("state", "IDLE")},
                    msg_id=f"hb-{envelope.id}",
                ),
            )
            return

        if envelope.type in {"stop", "interaction.touch", "dialogue.cancel"}:
            # Phase 1：記錄並 ack；音訊取消留 Phase 2
            await self._send(
                websocket,
                make_envelope("ack", {"ok": True, "reply_to": envelope.id, "scope": envelope.type}),
            )
            return

        await self._send(
            websocket,
            make_envelope("ack", {"ok": True, "reply_to": envelope.id}),
        )

    async def push(self, envelope: Envelope) -> dict[str, Any]:
        """由管理 API 或內部模組下發指令；無 Companion 活動會話則拒絕。"""
        try:
            validate_push_command(envelope, max_text_chars=self.max_text_chars)
        except ProtocolError as exc:
            return {"ok": False, "error": exc.code, "message": exc.message}

        if envelope.type not in {"hello.ok", "heartbeat", "ack"} and not self.can_push_companion_ui():
            return {"ok": False, "error": "not_companion", "message": "無 Companion 活動會話，拒絕推送"}

        ws = self.session.websocket
        if ws is None or ws.client_state != WebSocketState.CONNECTED:
            return {"ok": False, "error": "not_connected", "message": "裝置未連線"}

        await self._send(ws, envelope)
        return {"ok": True, "id": envelope.id, "type": envelope.type}

    async def _send(self, websocket: WebSocket, envelope: Envelope) -> None:
        await websocket.send_json(envelope.to_dict())

    async def _clear_if_current(self, websocket: WebSocket) -> None:
        async with self._lock:
            if self.session.websocket is websocket:
                self.session.websocket = None
                self.session.active = False
                self.session.mode = "offline"
                self.session.session_id = None
