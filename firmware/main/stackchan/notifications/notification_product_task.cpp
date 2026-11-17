#include "notification_product_task.h"

#include "notification_product_runtime.h"
#include "notification_utc_clock.h"

#include <atomic>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <new>
#include <sdkconfig.h>

namespace stackchan::notifications {
#if CONFIG_STACKCHAN_AGENT_NOTIFICATIONS
namespace {
std::atomic_flag worker_active = ATOMIC_FLAG_INIT;
std::atomic<bool> xiaozhi_busy{true};
constexpr unsigned kWorkerStackBytes = 8192;
constexpr unsigned kWorkerPriority = 2;

void runNotificationProductStream(void* argument)
{
    auto* request = static_cast<std::uint64_t*>(argument);
    const auto generation = *request;
    delete request;
    initNotificationProductRuntime();
    if (fetchAndArmNotificationProductRuntime(generation)) {
        while (isNotificationProductStreamArmed()) {
            const auto now_ms = static_cast<std::uint64_t>(esp_timer_get_time() / 1000);
            tickNotificationProductRuntime(now_ms, notificationUtcMs(), xiaozhi_busy.load());
            if (isNotificationProductStreamArmed()) {
                vTaskDelay(pdMS_TO_TICKS(20));
            }
        }
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
}  // namespace stackchan::notifications
