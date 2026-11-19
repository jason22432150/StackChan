#include "personal_pending_poll.h"

#include <string_view>

#ifdef ESP_PLATFORM
#include <esp_log.h>
#endif

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
    // Xiaozhi 對話中不拉 pending，避免 HTTP／lwIP 與 UDP receive task 搶內部 SRAM。
    if (!xiaozhi_busy && personalPendingFetchDue(last_fetch_ms, now_ms, interval_ms)) {
        if (auto result = client.fetch(http)) {
            const auto fed = feedPersonalPendingNotificationJson(result->body, now_ms, utc_ms);
#ifdef ESP_PLATFORM
            ESP_LOGI("AgentNotify", "personal pending fetch ok bytes=%u fed=%u",
                     static_cast<unsigned>(result->body.size()), static_cast<unsigned>(fed));
#else
            (void)fed;
#endif
        } else {
#ifdef ESP_PLATFORM
            ESP_LOGW("AgentNotify", "personal pending fetch failed host=%s port=%u",
                     http.coordinator_host.c_str(), static_cast<unsigned>(http.port));
#endif
        }
        // 成功或失敗都推進間隔，避免 20ms tick 打爆網路。
        last_fetch_ms = now_ms == 0 ? 1 : now_ms;
    }
    tickNotificationProductRuntime(now_ms, utc_ms, xiaozhi_busy);
    return isPersonalPendingNotificationArmed();
}

}  // namespace stackchan::notifications
