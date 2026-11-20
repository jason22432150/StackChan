"""裝置 WebSocket 介面骨架（Phase 0：尚未實作通訊）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DeviceSession:
    """Companion 活動會話狀態；無 active session 時不可推送通知／動畫。"""

    device_id: str | None = None
    session_id: str | None = None
    mode: str = "offline"
    active: bool = False


@dataclass
class DeviceWsHub:
    """Phase 1 將承載 /ws/device；此處只保留可測的狀態容器。"""

    session: DeviceSession = field(default_factory=DeviceSession)

    def set_mode(self, mode: str, *, active: bool) -> None:
        self.session.mode = mode
        self.session.active = active

    def can_push_companion_ui(self) -> bool:
        return self.session.active and self.session.mode == "companion"
