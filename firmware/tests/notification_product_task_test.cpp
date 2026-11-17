#include <cstdlib>
#include <esp_timer.h>
#include <freertos/task.h>
#include <iostream>
#include <stackchan/notifications/notification_product_runtime.h>
#include <stackchan/notifications/notification_product_task.h>
#include <stackchan/notifications/notification_utc_clock.h>

using stackchan::notifications::publishNotificationXiaozhiBusy;
using stackchan::notifications::NotificationStreamRequestResult;
using stackchan::notifications::requestConfiguredNotificationProductStream;
using stackchan::notifications::requestNotificationProductStream;

namespace {
TaskFunction_t scheduled_task = nullptr;
void* scheduled_argument = nullptr;
bool create_succeeds = false;
bool bootstrap_succeeds = false;
bool armed = false;
std::uint64_t utc_ms = 0;
std::uint64_t bootstrapped_generation = 0;
unsigned created = 0;
unsigned deleted = 0;
unsigned initialized = 0;
unsigned bootstrapped = 0;
unsigned polled = 0;
unsigned delays = 0;

void expect(bool passed, const char* message)
{
    if (!passed) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

void runScheduledTask()
{
    expect(scheduled_task != nullptr, "worker was scheduled");
    const auto entry = scheduled_task;
    scheduled_task = nullptr;
    entry(scheduled_argument);
}
}  // namespace

BaseType_t xTaskCreate(TaskFunction_t entry, const char*, unsigned, void* argument, unsigned, TaskHandle_t*)
{
    ++created;
    if (!create_succeeds) {
        return 0;
    }
    expect(scheduled_task == nullptr, "at most one worker is scheduled");
    scheduled_task = entry;
    scheduled_argument = argument;
    return pdPASS;
}

void vTaskDelay(TickType_t ticks)
{
    expect(ticks == pdMS_TO_TICKS(20), "worker uses the notification poll interval");
    ++delays;
    publishNotificationXiaozhiBusy(false);
}

void vTaskDelete(TaskHandle_t task)
{
    expect(task == nullptr, "worker deletes itself");
    ++deleted;
}

std::int64_t esp_timer_get_time() { return 123456; }

namespace stackchan::notifications {
std::uint64_t notificationUtcMs() noexcept { return utc_ms; }
void initNotificationProductRuntime() { ++initialized; }
bool fetchAndArmNotificationProductRuntime(std::uint64_t generation)
{
    ++bootstrapped;
    bootstrapped_generation = generation;
    expect(!requestNotificationProductStream(99), "bootstrap excludes another worker");
    armed = bootstrap_succeeds;
    return armed;
}
bool isNotificationProductStreamArmed() { return armed; }
void tickNotificationProductRuntime(std::uint64_t now, std::uint64_t utc, bool busy)
{
    ++polled;
    expect(now == 123 && utc == utc_ms, "tick receives monotonic and wall clock milliseconds");
    expect(busy == (polled == 1), "worker observes both published activity states");
    expect(!requestNotificationProductStream(99), "active stream excludes another worker");
    armed = polled < 2;
}
}  // namespace stackchan::notifications

int main()
{
    for (const auto* input : {"", " 1", "1 ", "+1", "-1", "1x", "18446744073709551616", "000000000000000000001"}) {
        expect(requestConfiguredNotificationProductStream(input) == NotificationStreamRequestResult::InvalidGeneration,
               "absent, malformed and overflowing generations are rejected");
    }
    expect(created == 0, "invalid generation never creates a task");
    expect(!requestNotificationProductStream(0) && created == 0, "unsynchronized UTC creates no worker");
    utc_ms = 5000;
#if CONFIG_STACKCHAN_AGENT_NOTIFICATIONS
    expect(!requestNotificationProductStream(7) && created == 1, "task allocation failure rejects request");
    create_succeeds = true;
    constexpr auto generation = UINT64_MAX;
    expect(requestConfiguredNotificationProductStream("18446744073709551615") ==
               NotificationStreamRequestResult::Scheduled,
           "retry accepts the largest valid generation");
    expect(initialized == 0 && bootstrapped == 0 && polled == 0, "caller does not run the runtime or TLS");
    expect(!requestNotificationProductStream(9) && created == 2, "pending worker rejects a duplicate");
    runScheduledTask();
    expect(initialized == 1 && bootstrapped == 1 && bootstrapped_generation == generation &&
               polled == 0 && deleted == 1,
           "failed bootstrap preserves uint64 generation and exits without polling");

    bootstrap_succeeds = true;
    publishNotificationXiaozhiBusy(true);
    expect(requestConfiguredNotificationProductStream("0") == NotificationStreamRequestResult::Scheduled,
           "bootstrap failure allows another request with generation zero");
    runScheduledTask();
    expect(initialized == 2 && bootstrapped == 2 && bootstrapped_generation == 0 &&
               polled == 2 && delays == 1 && deleted == 2,
           "successful worker polls until disconnection and exits");
    bootstrap_succeeds = false;
    expect(requestNotificationProductStream(27), "disconnect allows an explicit new request");
    runScheduledTask();
    expect(bootstrapped_generation == 27 && polled == 2 && deleted == 3, "no automatic reconnect");
#else
    expect(!requestNotificationProductStream(7) && created == 0, "disabled feature does not create tasks");
    expect(requestConfiguredNotificationProductStream("7") == NotificationStreamRequestResult::Rejected && created == 0,
           "configured request cannot bypass the disabled feature");
#endif
}
