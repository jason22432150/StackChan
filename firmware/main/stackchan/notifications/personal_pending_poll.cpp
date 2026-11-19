#include "personal_pending_poll.h"

#include <string_view>

namespace stackchan::notifications {
// 避免拉進 device_stream_tls／esp_transport；由 runtime 提供實作。
bool isPersonalPendingNotificationArmed();
std::size_t feedPersonalPendingNotificationJson(std::string_view pending_json, std::uint64_t now_ms,
                                                std::uint64_t utc_ms);
void tickNotificationProductRuntime(std::uint64_t now_ms, std::uint64_t utc_ms, bool xiaozhi_busy);

bool personalPendingFetchDue(std::uint64_t last_fetch_ms, std::uint64_t now_ms,
                             std::uint64_t interval_ms)
{
    if (interval_ms == 0) {
        return false;
    }
    if (last_fetch_ms == 0) {
        return true;
    }
    return now_ms >= last_fetch_ms && now_ms - last_fetch_ms >= interval_ms;
}

bool personalPendingPollOnce(std::uint64_t& last_fetch_ms, std::uint64_t interval_ms,
                             const PersonalPendingHttpClient::Config& http,
                             PersonalPendingHttpClient& client, std::uint64_t now_ms,
                             std::uint64_t utc_ms, bool xiaozhi_busy)
{
    if (!isPersonalPendingNotificationArmed()) {
        return false;
    }
    if (personalPendingFetchDue(last_fetch_ms, now_ms, interval_ms)) {
        if (auto result = client.fetch(http)) {
            (void)feedPersonalPendingNotificationJson(result->body, now_ms, utc_ms);
        }
        // 成功或失敗都推進間隔，避免 20ms tick 打爆網路。
        last_fetch_ms = now_ms == 0 ? 1 : now_ms;
    }
    tickNotificationProductRuntime(now_ms, utc_ms, xiaozhi_busy);
    return isPersonalPendingNotificationArmed();
}

}  // namespace stackchan::notifications
