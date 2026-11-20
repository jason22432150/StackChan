"""設定載入：YAML 檔案（Phase 0）。

Phase 0 僅讀取 YAML；API Key 等機密請用本機 `.env`／環境變數由後續 Provider
自行讀取，不寫入 Settings。環境變數覆寫 Settings 欄位留待 Phase 1。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class QuietHoursConfig(BaseModel):
    start: str = "23:00"
    end: str = "08:00"


class AppConfig(BaseModel):
    timezone: str = "Asia/Taipei"
    host: str = "0.0.0.0"
    port: int = 8765
    log_level: str = "INFO"


class DeviceConfig(BaseModel):
    boot_mode: str = "companion"
    heartbeat_seconds: int = 5
    session_timeout_seconds: int = 15
    max_text_chars: int = 160
    # LAN 配對 Token；正式環境請用環境變數 STACKCHAN_DEVICE_TOKEN 覆寫，勿提交真實值
    token: str = ""


class LlmConfig(BaseModel):
    active_provider: str = "provider_a"
    providers: list[str] = Field(default_factory=lambda: ["provider_a", "provider_b"])
    timeout_seconds: int = 25
    max_pet_plans_per_day: int = 48
    daily_spend_usd_soft_limit: float = 1.0


class VoiceConfig(BaseModel):
    activation: list[str] = Field(default_factory=lambda: ["touch", "keyword"])
    keyword_name: str = "小智"
    interrupt: str = "touch"
    raw_audio_retention: bool = False


class PetConfig(BaseModel):
    personality: str = "natural"
    mood_initial: int = 50
    energy_initial: int = 70
    interests_initial: int = 50
    action_min_seconds: int = 30
    action_max_seconds: int = 1200
    recent_activity_window: int = 20


class ProactivityConfig(BaseModel):
    focus_mode: bool = False
    quiet_hours: QuietHoursConfig = Field(default_factory=QuietHoursConfig)
    voice_max_per_day: int = 3
    voice_min_interval_minutes: int = 90
    bubble_min_interval_minutes: int = 20
    bubble_max_interval_minutes: int = 60


class NotificationsConfig(BaseModel):
    companion_only: bool = True
    max_resume_summary: int = 5
    retention_days: int = 7


class StorageConfig(BaseModel):
    db_path: str = "./data/companion.db"
    raw_audio_save: bool = False


class Settings(BaseModel):
    """Coordinator 完整設定。"""

    app: AppConfig = Field(default_factory=AppConfig)
    device: DeviceConfig = Field(default_factory=DeviceConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    pet: PetConfig = Field(default_factory=PetConfig)
    proactivity: ProactivityConfig = Field(default_factory=ProactivityConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    def public_dict(self) -> dict[str, Any]:
        """回傳可對外顯示的設定（不含任何金鑰）。"""
        return self.model_dump()


def _default_config_candidates(explicit: Path | None = None) -> list[Path]:
    if explicit is not None:
        return [explicit]
    root = Path(__file__).resolve().parent.parent
    return [root / "config.yaml", root / "config.example.yaml"]


def load_settings(config_path: Path | None = None) -> Settings:
    """
    讀取 YAML 設定。

    優先順序：明確路徑 → config.yaml → config.example.yaml → 內建預設。
    """
    data: dict[str, Any] = {}
    for candidate in _default_config_candidates(config_path):
        if candidate.is_file():
            with candidate.open("r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"設定檔格式錯誤（需為 mapping）: {candidate}")
            data = loaded
            break
    return Settings.model_validate(data)
