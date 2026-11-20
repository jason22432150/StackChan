"""主動互動 Gate 骨架（Phase 0：規則可單測，不連 TTS）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ProactivityDecision:
    allowed: bool
    reason: str


@dataclass
class ProactivityGate:
    focus_mode: bool = False
    quiet_start: str = "23:00"
    quiet_end: str = "08:00"
    voice_max_per_day: int = 3
    voice_min_interval_minutes: int = 90
    timezone: str = "Asia/Taipei"
    voice_count_today: int = 0
    last_voice_at: datetime | None = None

    def _parse_hhmm(self, value: str) -> time:
        hour, minute = value.split(":")
        return time(hour=int(hour), minute=int(minute))

    def in_quiet_hours(self, now: datetime | None = None) -> bool:
        tz = ZoneInfo(self.timezone)
        current = now.astimezone(tz) if now else datetime.now(tz)
        start = self._parse_hhmm(self.quiet_start)
        end = self._parse_hhmm(self.quiet_end)
        t = current.timetz().replace(tzinfo=None)
        if start <= end:
            return start <= t < end
        # 跨午夜，例如 23:00–08:00
        return t >= start or t < end

    def allow_voice(
        self,
        *,
        device_mode: str,
        companion_active: bool,
        user_dialogue_active: bool,
        speaking: bool,
        now: datetime | None = None,
    ) -> ProactivityDecision:
        if not companion_active or device_mode != "companion":
            return ProactivityDecision(False, "not_companion")
        if user_dialogue_active or speaking:
            return ProactivityDecision(False, "user_busy")
        if self.focus_mode:
            return ProactivityDecision(False, "focus_mode")
        if self.in_quiet_hours(now):
            return ProactivityDecision(False, "quiet_hours")
        if self.voice_count_today >= self.voice_max_per_day:
            return ProactivityDecision(False, "daily_limit")
        if self.last_voice_at is not None:
            current = now or datetime.now(ZoneInfo(self.timezone))
            delta_min = (current - self.last_voice_at).total_seconds() / 60.0
            if delta_min < self.voice_min_interval_minutes:
                return ProactivityDecision(False, "min_interval")
        return ProactivityDecision(True, "ok")
