"""P2-04 正式容量／逾時預設（對齊 CoreS3 MVP profile）。

依據 P0-04 CoreS3 基準：最大更新間隔 184,054 µs（軟路徑取 ceil=185 ms）、
LVGL 最大持鎖約 117 ms、內部 heap 低水位約 5.4 KiB。裝置端硬上限 capacity=4；
心跳／穩定門檻與 firmware `kCoreS3MvpRuntimeProfile` 對齊。R-006 軟體預算
4185 ms 僅供軟體驗收；實機失聯撤銷時間尚未量測，不得宣稱最終生產上界。
"""

from __future__ import annotations

from dataclasses import dataclass

# ceil(184_054 µs) — 與 firmware kP004MaxUiUpdateGapMs 對齊（R-006 軟路徑偏斜）。
P004_MAX_UI_UPDATE_GAP_MS = 185


@dataclass(frozen=True, slots=True)
class CoordinatorRuntimeLimits:
    """Coordinator 派送與 device-stream 對齊的 MVP 預設。"""

    device_queue_capacity: int = 4
    heartbeat_timeout_seconds: float = 4.0
    stability_seconds: float = 5.0
    heartbeat_interval_seconds: float = 1.0
    pong_timeout_seconds: float = 2.0
    max_frame_age_seconds: float = 5.0
    max_frame_bytes: int = 1024


CORE_S3_MVP_RUNTIME_LIMITS = CoordinatorRuntimeLimits()


def mvp_soft_worst_case_revoke_ms(
    limits: CoordinatorRuntimeLimits = CORE_S3_MVP_RUNTIME_LIMITS,
) -> int:
    """R-006 軟體失聯→撤銷預算（ms）：heartbeat_timeout + P0-04 UI gap。

    非實機量測值；僅供契約對齊與 host／pytest 驗收。
    """
    return int(limits.heartbeat_timeout_seconds * 1000) + P004_MAX_UI_UPDATE_GAP_MS


def validate_coordinator_runtime_limits(limits: CoordinatorRuntimeLimits) -> CoordinatorRuntimeLimits:
    """Fail-Closed：非正值或超過保守天花板的設定不可用於派送。"""
    if (
        limits.device_queue_capacity < 1
        or limits.device_queue_capacity > 4
        or limits.heartbeat_timeout_seconds <= 0
        or limits.heartbeat_timeout_seconds > 60
        or limits.stability_seconds <= 0
        or limits.stability_seconds > 60
        or limits.heartbeat_interval_seconds <= 0
        or limits.heartbeat_interval_seconds > limits.heartbeat_timeout_seconds
        or limits.pong_timeout_seconds <= 0
        or limits.pong_timeout_seconds > 60
        or limits.max_frame_age_seconds <= 0
        or limits.max_frame_age_seconds > 60
        or limits.max_frame_bytes < 1
        or limits.max_frame_bytes > 4096
    ):
        raise ValueError("Coordinator runtime limits 超出允許範圍")
    return limits
