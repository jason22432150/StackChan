#include "notification_product_task.h"

#include "notification_product_runtime.h"
#include "notification_utc_clock.h"

#include <atomic>
#include <charconv>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <new>
#include <sdkconfig.h>

#if CONFIG_STACKCHAN_AGENT_NOTIFICATIONS && CONFIG_STACKCHAN_RUNTIME_BASELINE
#include <esp_heap_caps.h>
#include <esp_log.h>
#endif

namespace stackchan::notifications {
#if CONFIG_STACKCHAN_AGENT_NOTIFICATIONS
namespace {
std::atomic_flag worker_active = ATOMIC_FLAG_INIT;
std::atomic<bool> xiaozhi_busy{true};
constexpr unsigned kWorkerStackBytes = 8192;
constexpr unsigned kWorkerPriority = 2;

#if CONFIG_STACKCHAN_RUNTIME_BASELINE
void logNotificationResources(const char* phase)
{
    constexpr auto internal_caps = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
    ESP_LOGI("AgentNotify",
             "AGENT_NOTIFY_RESOURCE phase=%s stack_min_free_bytes=%u"
             " internal_free_bytes=%zu internal_min_since_boot_bytes=%zu internal_largest_block_bytes=%zu",
             phase, static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr)),
             heap_caps_get_free_size(internal_caps), heap_caps_get_minimum_free_size(internal_caps),
             heap_caps_get_largest_free_block(internal_caps));
}
#endif

void runNotificationProductStream(void* argument)
{
    auto* request = static_cast<std::uint64_t*>(argument);
    const auto generation = *request;
    delete request;
    initNotificationProductRuntime();
    const bool upgraded = fetchAndArmNotificationProductRuntime(generation);
#if CONFIG_STACKCHAN_RUNTIME_BASELINE
    logNotificationResources(upgraded ? "upgraded" : "bootstrap_failed");
#endif
    if (upgraded) {
        while (isNotificationProductStreamArmed()) {
            const auto now_ms = static_cast<std::uint64_t>(esp_timer_get_time() / 1000);
            tickNotificationProductRuntime(now_ms, notificationUtcMs(), xiaozhi_busy.load());
            if (isNotificationProductStreamArmed()) {
                vTaskDelay(pdMS_TO_TICKS(20));
            }
        }
#if CONFIG_STACKCHAN_RUNTIME_BASELINE
        logNotificationResources("disconnected");
#endif
    }
    worker_active.clear();
    vTaskDelete(nullptr);
}
}  // namespace

void publishNotificationXiaozhiBusy(bool busy) noexcept
{
    xiaozhi_busy.store(busy);
}

bool requestNotificationProductStream(std::uint64_t coordinator_generation)
{
    if (notificationUtcMs() == 0 || worker_active.test_and_set()) {
        return false;
    }
    auto* generation = new (std::nothrow) std::uint64_t(coordinator_generation);
    if (!generation ||
        xTaskCreate(runNotificationProductStream, "agent_notify", kWorkerStackBytes, generation,
                    kWorkerPriority, nullptr) != pdPASS) {
        delete generation;
        worker_active.clear();
        return false;
    }
    // A successful task creation transfers the argument to the worker.
    return true;
}
#else
bool requestNotificationProductStream(std::uint64_t) { return false; }
void publishNotificationXiaozhiBusy(bool) noexcept {}
#endif

NotificationStreamRequestResult requestConfiguredNotificationProductStream(std::string_view generation)
{
    std::uint64_t value = 0;
    if (generation.empty() || generation.size() > 20) {
        return NotificationStreamRequestResult::InvalidGeneration;
    }
    const auto* end = generation.data() + generation.size();
    const auto [parsed_end, error] = std::from_chars(generation.data(), end, value);
    if (error != std::errc{} || parsed_end != end) {
        return NotificationStreamRequestResult::InvalidGeneration;
    }
    return requestNotificationProductStream(value) ? NotificationStreamRequestResult::Scheduled
                                                   : NotificationStreamRequestResult::Rejected;
}
}  // namespace stackchan::notifications
