#pragma once

#include "runtime_limits.h"

namespace stackchan::notifications {

/**
 * R-006 軟路徑：軟體推導的失聯→撤銷上界（非實機量測生產值）。
 *
 * 公式：heartbeat_timeout_ms + kP004MaxUiUpdateGapMs
 * - heartbeat_timeout_ms：Controller 判定靜默失聯的門檻（狀態檢查當下）。
 * - kP004MaxUiUpdateGapMs：P0-04 實測最大 UI 更新間隔 ceil(184,054 µs)=185 ms，
 *   作為「下一次 poll／狀態檢查」可能延遲的軟體偏斜上界。
 *
 * FailClosedGuard.poll 在偵測到 Suspended 後同步 interrupt，不另加網路 RTT。
 * Transport 顯式斷線路徑通常遠小於本預算。實機 Gate 必須重新量測後才能關閉 R-006。
 */
inline constexpr NotificationController::Tick kP004MaxUiUpdateGapMs = 185;

/** 依 profile 計算軟體最壞撤銷預算（ms）。非法／未 sanitize 的 profile 呼叫端不應使用。 */
constexpr NotificationController::Tick softWorstCaseRevokeMs(const NotificationRuntimeProfile& profile)
{
    return profile.controller.heartbeat_timeout_ms + kP004MaxUiUpdateGapMs;
}

/** MVP 預設軟體預算：4000 + 185 = 4185 ms。 */
inline constexpr NotificationController::Tick kMvpSoftWorstCaseRevokeMs =
    softWorstCaseRevokeMs(kCoreS3MvpRuntimeProfile);

/** link_anchor／測試：回傳 MVP 軟體預算（不執行網路／UI）。 */
NotificationController::Tick mvpSoftWorstCaseRevokeMs();

}  // namespace stackchan::notifications
