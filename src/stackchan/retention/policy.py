"""
短期保留政策。

規格明確：7／14／30 日為候選、尚未鎖死正式產品預設。
此處 DEFAULT_RETENTION_DAYS=14 僅作可配置候選起點，並寫入版本化設定。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from stackchan.coordinator import CoordinatorStore, CoordinatorStoreError

RETENTION_DAY_CANDIDATES = (7, 14, 30)
DEFAULT_RETENTION_DAYS = 14
SETTING_KEY = "retention_days"


class RetentionError(ValueError):
    """保留政策錯誤。"""


@dataclass(frozen=True, slots=True)
class CleanupReport:
    """清理結果。"""

    retention_days: int
    settings_version: int
    cutoff_iso: str
    purged_event_ids: list[str]
    watermark: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _fmt(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


class RetentionService:
    """Coordinator 版本化保留設定與清理編排。"""

    def __init__(self, store: CoordinatorStore) -> None:
        self._store = store

    def ensure_default_settings(self) -> int:
        """若尚未設定，寫入候選預設 retention_days。"""
        if self._store.get_setting_version(SETTING_KEY) == 0:
            return self.set_retention_days(DEFAULT_RETENTION_DAYS)
        return self._store.get_setting_version(SETTING_KEY)

    def set_retention_days(self, days: int) -> int:
        if days not in RETENTION_DAY_CANDIDATES:
            raise RetentionError(
                f"retention_days={days} 不在候選 {RETENTION_DAY_CANDIDATES}；"
                "正式預設天數尚未鎖定，僅允許候選值"
            )
        return self._store.set_setting(SETTING_KEY, days)

    def get_retention_days(self) -> int:
        value = self._store.get_setting(SETTING_KEY, DEFAULT_RETENTION_DAYS)
        if not isinstance(value, int):
            raise RetentionError("retention_days 設定型別錯誤")
        return value

    def run_cleanup(
        self,
        *,
        bridge_id: str,
        epoch: str,
        now: datetime | None = None,
    ) -> CleanupReport:
        self.ensure_default_settings()
        days = self.get_retention_days()
        current = now or _utc_now()
        cutoff = current - timedelta(days=days)
        cutoff_iso = _fmt(cutoff)
        try:
            purged = self._store.purge_eligible_events(
                bridge_id=bridge_id,
                epoch=epoch,
                cutoff_iso=cutoff_iso,
            )
        except CoordinatorStoreError as exc:
            raise RetentionError(str(exc)) from exc
        return CleanupReport(
            retention_days=days,
            settings_version=self._store.get_setting_version(SETTING_KEY),
            cutoff_iso=cutoff_iso,
            purged_event_ids=purged,
            watermark=self._store.get_cleanup_watermark(bridge_id, epoch),
        )

    def settings_snapshot(self) -> dict[str, Any]:
        return {
            "retention_days": self.get_retention_days(),
            "retention_days_version": self._store.get_setting_version(SETTING_KEY),
            "candidates": list(RETENTION_DAY_CANDIDATES),
            "default_is_locked_product_value": False,
        }
