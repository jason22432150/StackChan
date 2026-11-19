#pragma once

#include "personal_pending_http_client.h"

#include <cstdint>

namespace stackchan::notifications {

/** 預設每 5s 拉一次 pending（LVGL／tick 仍 20ms）。 */
inline constexpr std::uint64_t kDefaultPersonalPendingFetchIntervalMs = 5000;

/** last_fetch_ms==0 視為尚未拉過 → due。interval_ms==0 永不 due。 */
bool personalPendingFetchDue(std::uint64_t last_fetch_ms, std::uint64_t now_ms,
                             std::uint64_t interval_ms);

/**
 * 一輪個人版 worker：due 且非 Xiaozhi busy 時 fetch→feed（失敗只跳過，仍更新 last_fetch），再 tick。
 * busy 時跳過 fetch（不推進 last_fetch），仍 tick 以利搶占 UI。
 * 回傳 tick 後是否仍 armed。
 */
bool personalPendingPollOnce(std::uint64_t& last_fetch_ms, std::uint64_t interval_ms,
                             const PersonalPendingHttpClient::Config& http,
                             PersonalPendingHttpClient& client, std::uint64_t now_ms,
                             std::uint64_t utc_ms, bool xiaozhi_busy);

}  // namespace stackchan::notifications
