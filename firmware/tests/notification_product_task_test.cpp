#include <cstdlib>
#include <esp_timer.h>
#include <freertos/task.h>
#include <iostream>
#include <stackchan/notifications/notification_product_runtime.h>
#include <stackchan/notifications/notification_pairing_client.h>
#include <stackchan/notifications/notification_product_task.h>
#include <stackchan/notifications/notification_utc_clock.h>
#include <stackchan/notifications/personal_pending_http_client.h>
#include <stackchan/notifications/personal_pending_json.h>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#if CONFIG_STACKCHAN_RUNTIME_BASELINE
#include <esp_heap_caps.h>
#include <esp_log.h>
#endif

using stackchan::notifications::publishNotificationXiaozhiBusy;
using stackchan::notifications::NotificationStreamRequestResult;
using stackchan::notifications::NotificationBootstrapResult;
using stackchan::notifications::requestConfiguredNotificationProductStream;
using stackchan::notifications::requestNotificationProductStream;

namespace {
TaskFunction_t scheduled_task = nullptr;
void* scheduled_argument = nullptr;
bool create_succeeds = false;
auto bootstrap_result = NotificationBootstrapResult::CredentialsUnavailable;
bool armed = false;
std::uint64_t utc_ms = 0;
std::uint64_t bootstrapped_generation = 0;
unsigned created = 0;
unsigned deleted = 0;
unsigned initialized = 0;
unsigned bootstrapped = 0;
unsigned polled = 0;
unsigned delays = 0;
unsigned pairing_starts = 0;
unsigned pairing_completions = 0;
unsigned pairing_cancels = 0;
unsigned discarded_grants = 0;
bool pairing_start_succeeds = false;
bool cancel_on_delay = false;
bool cancel_on_delivery = false;
unsigned pending_completions = 0;
auto completion = stackchan::notifications::NotificationPairingClient::Completion::Unavailable;
const stackchan::notifications::NotificationPairingEndpoint pairing_endpoint{
    "coordinator.example", 9443, "-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----",
};
bool personal_armed = false;
bool personal_arm_ok = true;
unsigned personal_armed_count = 0;
unsigned personal_feeds = 0;
unsigned personal_fetches = 0;
std::string personal_feed_body;
#if CONFIG_STACKCHAN_RUNTIME_BASELINE
std::vector<std::pair<std::string_view, std::string_view>> resource_samples;
#endif

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
    if (ticks == pdMS_TO_TICKS(1000)) {
        const auto snapshot = stackchan::notifications::notificationProductPairingStatus();
        expect(snapshot.state == stackchan::notifications::NotificationPairingState::AwaitingApproval &&
                   std::string_view(snapshot.user_code.data()) == "CODE12",
               "UI can read the code while background pairing waits");
        if (cancel_on_delay) {
            stackchan::notifications::cancelNotificationProductPairing();
        }
        return;
    }
    expect(ticks == pdMS_TO_TICKS(20), "worker uses the notification poll interval");
    ++delays;
    publishNotificationXiaozhiBusy(false);
}

void vTaskDelete(TaskHandle_t task)
{
    expect(task == nullptr, "worker deletes itself");
    ++deleted;
}

#if CONFIG_STACKCHAN_RUNTIME_BASELINE
unsigned uxTaskGetStackHighWaterMark(TaskHandle_t task)
{
    expect(task == nullptr, "sample the notification task's own stack");
    return 1536;
}

std::size_t heap_caps_get_free_size(unsigned caps)
{
    expect(caps == (MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT), "sample internal 8-bit heap");
    return 6000;
}

std::size_t heap_caps_get_minimum_free_size(unsigned caps)
{
    expect(caps == (MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT), "sample internal heap minimum since boot");
    return 4000;
}

std::size_t heap_caps_get_largest_free_block(unsigned caps)
{
    expect(caps == (MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT), "sample largest contiguous internal block");
    return 3072;
}

void ESP_LOGI(const char* tag, const char* format, const char* phase, unsigned stack,
              std::size_t free, std::size_t minimum, std::size_t largest, const char* result)
{
    expect(std::string_view(tag) == "AgentNotify" && std::string_view(format).starts_with("AGENT_NOTIFY_RESOURCE "),
           "use the fixed resource log tag and prefix");
    expect(stack == 1536 && free == 6000 && minimum == 4000 && largest == 3072,
           "log resource samples in bytes");
    expect(std::string_view(format).ends_with(" bootstrap_result=%s"), "log a fixed bootstrap result field");
    resource_samples.emplace_back(phase, result);
}
#endif

std::int64_t esp_timer_get_time() { return 123456; }

namespace stackchan::notifications {
std::optional<std::string> NotificationPairingClient::start(NotificationPairingEndpoint endpoint, std::uint16_t port)
{
    ++pairing_starts;
    expect(endpoint.coordinator_host == pairing_endpoint.coordinator_host && endpoint.port == 9443 && port == 8443,
           "worker passes both endpoint ports");
    expect(!requestNotificationProductStream(1) && !requestNotificationProductPairing(pairing_endpoint, 8443, 1),
           "pairing excludes stream and another pairing worker");
    return pairing_start_succeeds ? std::optional<std::string>("CODE12") : std::nullopt;
}
NotificationPairingClient::Completion NotificationPairingClient::complete()
{
    ++pairing_completions;
    if (pending_completions) {
        --pending_completions;
        return Completion::Pending;
    }
    if (cancel_on_delivery) {
        cancelNotificationProductPairing();
    }
    return completion;
}
void NotificationPairingClient::cancel() { ++pairing_cancels; }
void discardPendingNotificationProductCredentials() { ++discarded_grants; }
std::uint64_t notificationUtcMs() noexcept { return utc_ms; }
void initNotificationProductRuntime() { ++initialized; }
NotificationBootstrapResult fetchAndArmNotificationProductRuntime(std::uint64_t generation)
{
    ++bootstrapped;
    bootstrapped_generation = generation;
    expect(!requestNotificationProductStream(99), "bootstrap excludes another worker");
    armed = bootstrap_result == NotificationBootstrapResult::Upgraded;
    return bootstrap_result;
}
bool isNotificationProductStreamArmed() { return armed; }
bool armPersonalPendingNotificationProductRuntime(std::uint64_t, std::string_view, std::string_view,
                                                  std::uint64_t, std::uint64_t, std::uint64_t, std::uint64_t)
{
    ++personal_armed_count;
    personal_armed = personal_arm_ok;
    return personal_arm_ok;
}
bool isPersonalPendingNotificationArmed() { return personal_armed; }
void pausePersonalPendingNotificationProductRuntime() noexcept
{
    personal_armed = false;
}
bool trySchedulePersonalPendingBootAfterSntp(const char** reason)
{
    if (reason != nullptr) {
        *reason = "test_stub";
    }
    // host stub：不自動重排程，避免測試自旋
    return false;
}
std::size_t feedPersonalPendingNotificationJson(std::string_view body, std::uint64_t, std::uint64_t)
{
    ++personal_feeds;
    personal_feed_body.assign(body);
    return 1;
}
void tickNotificationProductRuntime(std::uint64_t now, std::uint64_t utc, bool busy)
{
    ++polled;
    if (personal_armed) {
        expect(now == 123 && utc == utc_ms, "personal tick clock");
        personal_armed = polled < 2;
        return;
    }
    expect(now == 123 && utc == utc_ms, "tick receives monotonic and wall clock milliseconds");
    expect(busy == (polled == 1), "worker observes both published activity states");
    expect(!requestNotificationProductStream(99), "active stream excludes another worker");
    armed = polled < 2;
}
std::optional<PersonalPendingHttpClient::Result> PersonalPendingHttpClient::fetch(const Config& config)
{
    ++personal_fetches;
    expect(config.device_id == "cores3_primary", "personal fetch device");
    return Result{std::string(R"({"items":[],"count":0})")};
}
bool PersonalPendingHttpClient::ack(const Config&, std::string_view)
{
    return true;
}
std::size_t collectPersonalPendingDeliveryIds(std::string_view, std::size_t, std::vector<std::string>& out,
                                              std::size_t)
{
    out.clear();
    return 0;
}
}  // namespace stackchan::notifications

int main()
{
    using namespace stackchan::notifications;
    expect(notificationProductPairingStatus().state == NotificationPairingState::Idle,
           "pairing status starts idle");
    expect(!requestNotificationProductPairing(pairing_endpoint, 8443, 1) && created == 0,
           "unsynchronized pairing schedules no worker");
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
#if CONFIG_STACKCHAN_RUNTIME_BASELINE
    expect(resource_samples.empty(), "rejected and queued requests log no worker resource samples");
#endif
    runScheduledTask();
    expect(initialized == 1 && bootstrapped == 1 && bootstrapped_generation == generation &&
               polled == 0 && deleted == 1,
           "failed bootstrap preserves uint64 generation and exits without polling");

    bootstrap_result = NotificationBootstrapResult::Upgraded;
    publishNotificationXiaozhiBusy(true);
    expect(requestConfiguredNotificationProductStream("0") == NotificationStreamRequestResult::Scheduled,
           "bootstrap failure allows another request with generation zero");
    runScheduledTask();
    expect(initialized == 2 && bootstrapped == 2 && bootstrapped_generation == 0 &&
               polled == 2 && delays == 1 && deleted == 2,
           "successful worker polls until disconnection and exits");
    bootstrap_result = NotificationBootstrapResult::StreamUpgradeFailed;
    expect(requestNotificationProductStream(27), "disconnect allows an explicit new request");
    runScheduledTask();
    expect(bootstrapped_generation == 27 && polled == 2 && deleted == 3, "no automatic reconnect");
#if CONFIG_STACKCHAN_RUNTIME_BASELINE
    expect(resource_samples == std::vector<std::pair<std::string_view, std::string_view>>{
               {"bootstrap_failed", "credentials_unavailable"},
               {"upgraded", "upgraded"},
               {"disconnected", "not_applicable"},
               {"bootstrap_failed", "stream_upgrade_failed"},
           },
           "sample exactly once at each worker transition");
#endif
    create_succeeds = false;
    expect(!requestNotificationProductPairing(pairing_endpoint, 8443, 1) &&
               notificationProductPairingStatus().state == NotificationPairingState::Failed,
           "pairing task allocation failure is observable and releases ownership");
    create_succeeds = true;
    const auto startPairing = [&] {
        expect(requestNotificationProductPairing(pairing_endpoint, 8443, 42), "local request schedules pairing");
        expect(notificationProductPairingStatus().state == NotificationPairingState::Starting &&
                   notificationProductPairingStatus().user_code[0] == '\0',
               "accepted request exposes Starting without a stale code");
    };
    auto before_start = pairing_starts;
    startPairing();
    expect(pairing_starts == before_start, "request returns before HTTPS starts");
    cancelNotificationProductPairing();
    runScheduledTask();
    expect(pairing_starts == before_start && notificationProductPairingStatus().state == NotificationPairingState::Cancelled,
           "cancel before execution prevents HTTPS");

    startPairing();
    runScheduledTask();
    expect(notificationProductPairingStatus().state == NotificationPairingState::Failed &&
               notificationProductPairingStatus().user_code[0] == '\0', "failed start clears the code");
    pairing_start_succeeds = true;
    completion = NotificationPairingClient::Completion::Pending;
    cancel_on_delay = true;
    startPairing();
    runScheduledTask();
    expect(notificationProductPairingStatus().state == NotificationPairingState::Cancelled &&
               notificationProductPairingStatus().user_code[0] == '\0', "cancel while waiting clears the code");
    cancel_on_delay = false;
    completion = NotificationPairingClient::Completion::Unavailable;
    startPairing();
    runScheduledTask();
    expect(notificationProductPairingStatus().state == NotificationPairingState::Failed,
           "unavailable pairing releases the worker");

    completion = NotificationPairingClient::Completion::Delivered;
    cancel_on_delivery = true;
    const auto previous_bootstraps = bootstrapped;
    startPairing();
    runScheduledTask();
    expect(discarded_grants == 1 && bootstrapped == previous_bootstraps &&
               notificationProductPairingStatus().state == NotificationPairingState::Cancelled,
           "cancellation during completion discards the grant before bootstrap");
    cancel_on_delivery = false;
    bootstrap_result = NotificationBootstrapResult::PolicyUnavailable;
    startPairing();
    runScheduledTask();
    expect(bootstrapped_generation == 42 && notificationProductPairingStatus().state == NotificationPairingState::Failed,
           "delivered pairing passes generation and reports policy failure");
    bootstrap_result = NotificationBootstrapResult::Upgraded;
    polled = 0;
    publishNotificationXiaozhiBusy(true);
    pending_completions = 1;
    startPairing();
    runScheduledTask();
    expect(polled == 2 && notificationProductPairingStatus().state == NotificationPairingState::Idle &&
               notificationProductPairingStatus().user_code[0] == '\0',
           "approved pairing enters the stream loop and returns idle after disconnect");

    PersonalPendingWorkerRequest personal{
        {"192.168.20.148", 8443, "", "device-token", "cores3_primary", 4096, 10000, 50},
        1,
        "pol_v1",
        1,
        9'000'000'000'000ULL,
        5000,
    };
    // 對話中拒排程；idle 才允許 personal pending worker。
    publishNotificationXiaozhiBusy(false);
    personal_arm_ok = false;
    polled = 0;
    personal_fetches = 0;
    personal_feeds = 0;
    personal_armed_count = 0;
    expect(requestPersonalPendingNotificationProduct(personal), "personal schedules worker");
    expect(!requestNotificationProductStream(1), "personal worker excludes stream");
    runScheduledTask();
    expect(personal_armed_count == 1 && personal_fetches == 0 && deleted >= 1, "arm failure exits without fetch");

    personal_arm_ok = true;
    personal_armed = false;
    polled = 0;
    personal_fetches = 0;
    personal_feeds = 0;
    publishNotificationXiaozhiBusy(false);
    expect(requestPersonalPendingNotificationProduct(personal), "personal armed path");
    runScheduledTask();
    expect(personal_armed_count >= 2 && personal_fetches >= 1 && personal_feeds >= 1 && polled == 2,
           "personal worker fetch→feed→tick until disarmed");

    // busy 時拒啟動，並標記稍後 resume
    publishNotificationXiaozhiBusy(true);
    expect(!requestPersonalPendingNotificationProduct(personal), "reject while Xiaozhi busy");
#else
    expect(!requestNotificationProductStream(7) && created == 0, "disabled feature does not create tasks");
    expect(requestConfiguredNotificationProductStream("7") == NotificationStreamRequestResult::Rejected && created == 0,
           "configured request cannot bypass the disabled feature");
    expect(!requestNotificationProductPairing(pairing_endpoint, 8443, 1) && created == 0,
           "disabled pairing creates no task");
    expect(!requestPersonalPendingNotificationProduct({}), "disabled personal pending creates no task");
    cancelNotificationProductPairing();
    expect(notificationProductPairingStatus().state == NotificationPairingState::Idle,
           "disabled feature remains idle");
#endif
}
