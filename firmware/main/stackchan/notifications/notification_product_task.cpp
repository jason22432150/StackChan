#include "notification_product_task.h"

#include "notification_product_runtime.h"
#include "notification_pairing_client.h"
#include "notification_utc_clock.h"
#include "personal_pending_http_client.h"
#include "personal_pending_poll.h"
#include "notification_controller.h"

#include <atomic>
#include <charconv>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <new>
#include <mutex>
#include <utility>
#include <algorithm>
#include <sdkconfig.h>

#if CONFIG_STACKCHAN_AGENT_NOTIFICATIONS
#if CONFIG_STACKCHAN_RUNTIME_BASELINE || (defined(CONFIG_SPIRAM) && CONFIG_SPIRAM)
#include <esp_heap_caps.h>
#endif
#if defined(ESP_PLATFORM) || CONFIG_STACKCHAN_RUNTIME_BASELINE
#include <esp_log.h>
#endif
#endif

namespace stackchan::notifications {
#if CONFIG_STACKCHAN_AGENT_NOTIFICATIONS
namespace {
std::atomic_flag worker_active = ATOMIC_FLAG_INIT;
std::atomic<bool> xiaozhi_busy{true};
constexpr unsigned kWorkerStackBytes = 8192;
constexpr unsigned kWorkerPriority = 2;
std::mutex pairing_status_mutex;
NotificationPairingStatus pairing_status;
std::atomic<bool> pairing_cancelled{false};

void setPairingStatus(NotificationPairingState state, std::string_view code = {})
{
    const std::lock_guard lock(pairing_status_mutex);
    pairing_status = {};
    pairing_status.state = state;
    std::copy_n(code.begin(), std::min(code.size(), pairing_status.user_code.size() - 1),
                pairing_status.user_code.begin());
}

struct PairingRequest {
    NotificationPairingEndpoint endpoint;
    std::uint16_t stream_port;
    std::uint64_t generation;
};

bool printableField(std::string_view text, std::size_t limit)
{
    return !text.empty() && text.size() <= limit &&
           std::all_of(text.begin(), text.end(), [](unsigned char c) { return c >= 0x21 && c <= 0x7e; });
}

#if CONFIG_STACKCHAN_RUNTIME_BASELINE
const char* bootstrapResultName(NotificationBootstrapResult result)
{
    switch (result) {
        case NotificationBootstrapResult::Upgraded: return "upgraded";
        case NotificationBootstrapResult::NotInitialized: return "not_initialized";
        case NotificationBootstrapResult::AlreadyArmed: return "already_armed";
        case NotificationBootstrapResult::ClockUnsynchronized: return "clock_unsynchronized";
        case NotificationBootstrapResult::CredentialsUnavailable: return "credentials_unavailable";
        case NotificationBootstrapResult::PolicyUnavailable: return "policy_unavailable";
        case NotificationBootstrapResult::StreamUpgradeFailed: return "stream_upgrade_failed";
    }
    return "unknown";
}

void logNotificationResources(const char* phase, const char* result)
{
    constexpr auto internal_caps = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
    ESP_LOGI("AgentNotify",
             "AGENT_NOTIFY_RESOURCE phase=%s stack_min_free_bytes=%u"
             " internal_free_bytes=%zu internal_min_since_boot_bytes=%zu internal_largest_block_bytes=%zu"
             " bootstrap_result=%s",
             phase, static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr)),
             heap_caps_get_free_size(internal_caps), heap_caps_get_minimum_free_size(internal_caps),
             heap_caps_get_largest_free_block(internal_caps), result);
}
#endif

void runProductStream(std::uint64_t generation, bool paired)
{
    initNotificationProductRuntime();
    const auto result = fetchAndArmNotificationProductRuntime(generation);
    const bool upgraded = result == NotificationBootstrapResult::Upgraded;
    if (paired) {
        setPairingStatus(upgraded ? NotificationPairingState::Connected : NotificationPairingState::Failed);
    }
#if CONFIG_STACKCHAN_RUNTIME_BASELINE
    logNotificationResources(upgraded ? "upgraded" : "bootstrap_failed", bootstrapResultName(result));
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
        logNotificationResources("disconnected", "not_applicable");
#endif
    }
    if (paired && upgraded) {
        setPairingStatus(NotificationPairingState::Idle);
    }
    worker_active.clear();
    vTaskDelete(nullptr);
}

void runNotificationProductStream(void* argument)
{
    auto* request = static_cast<std::uint64_t*>(argument);
    const auto generation = *request;
    delete request;
    runProductStream(generation, false);
}

bool pairUntilDelivered(PairingRequest* request)
{
    NotificationPairingClient client;
    auto code = pairing_cancelled.load() ? std::nullopt : client.start(std::move(request->endpoint), request->stream_port);
    delete request;
    if (code) {
        setPairingStatus(NotificationPairingState::AwaitingApproval, *code);
        while (!pairing_cancelled.load()) {
            const auto result = client.complete();
            if (result == NotificationPairingClient::Completion::Delivered) {
                if (pairing_cancelled.load()) {
                    discardPendingNotificationProductCredentials();
                    break;
                }
                // Once Connecting is published, the notification task owns the grant.
                setPairingStatus(NotificationPairingState::Connecting);
                client.cancel();
                return true;
            }
            if (result == NotificationPairingClient::Completion::Unavailable) {
                break;
            }
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    }
    client.cancel();
    setPairingStatus(pairing_cancelled.load() ? NotificationPairingState::Cancelled : NotificationPairingState::Failed);
    return false;
}

void runNotificationProductPairing(void* argument)
{
    auto* request = static_cast<PairingRequest*>(argument);
    const auto generation = request->generation;
    if (pairUntilDelivered(request)) {
        runProductStream(generation, true);
        return;
    }
    worker_active.clear();
    vTaskDelete(nullptr);
}

void runPersonalPendingWorker(void* argument)
{
    auto* request = static_cast<PersonalPendingWorkerRequest*>(argument);
    PersonalPendingWorkerRequest cfg = std::move(*request);
    delete request;

    initNotificationProductRuntime();
    const auto now_ms = static_cast<std::uint64_t>(esp_timer_get_time() / 1000);
    const auto utc_ms = notificationUtcMs();
    if (!armPersonalPendingNotificationProductRuntime(cfg.session, cfg.http.device_id, cfg.policy_version,
                                                      cfg.generation, cfg.policy_expires_utc_ms, utc_ms,
                                                      now_ms)) {
#if CONFIG_STACKCHAN_RUNTIME_BASELINE
        logNotificationResources("personal_arm_failed", "not_applicable");
#endif
        worker_active.clear();
        vTaskDelete(nullptr);
        return;
    }
#if CONFIG_STACKCHAN_RUNTIME_BASELINE
    logNotificationResources("personal_armed", "not_applicable");
#endif

    PersonalPendingHttpClient client;
    std::uint64_t last_fetch_ms = 0;
    while (isPersonalPendingNotificationArmed()) {
        const auto tick_now = static_cast<std::uint64_t>(esp_timer_get_time() / 1000);
        const auto tick_utc = notificationUtcMs();
        if (!personalPendingPollOnce(last_fetch_ms, cfg.fetch_interval_ms, cfg.http, client, tick_now, tick_utc,
                                     xiaozhi_busy.load())) {
            break;
        }
        if (isPersonalPendingNotificationArmed()) {
            vTaskDelay(pdMS_TO_TICKS(20));
        }
    }
#if CONFIG_STACKCHAN_RUNTIME_BASELINE
    logNotificationResources("personal_disconnected", "not_applicable");
#endif
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

bool requestNotificationProductPairing(NotificationPairingEndpoint endpoint, std::uint16_t stream_port,
                                       std::uint64_t coordinator_generation)
{
    if (notificationUtcMs() == 0 || stream_port == 0 || endpoint.port == 0 ||
        endpoint.coordinator_host.empty() || endpoint.coordinator_host.size() > 253 ||
        endpoint.coordinator_ca_pem.empty() || endpoint.coordinator_ca_pem.size() > 3999 ||
        worker_active.test_and_set()) {
        return false;
    }
    pairing_cancelled.store(false);
    setPairingStatus(NotificationPairingState::Starting);
    auto* request = new (std::nothrow) PairingRequest{std::move(endpoint), stream_port, coordinator_generation};
    if (!request || xTaskCreate(runNotificationProductPairing, "agent_pair", kWorkerStackBytes, request,
                               kWorkerPriority, nullptr) != pdPASS) {
        delete request;
        setPairingStatus(NotificationPairingState::Failed);
        worker_active.clear();
        return false;
    }
    return true;
}

NotificationPairingStatus notificationProductPairingStatus()
{
    const std::lock_guard lock(pairing_status_mutex);
    return pairing_status;
}

void cancelNotificationProductPairing() noexcept
{
    pairing_cancelled.store(true);
}

bool requestPersonalPendingNotificationProduct(PersonalPendingWorkerRequest request)
{
    if (notificationUtcMs() == 0) {
#ifdef ESP_PLATFORM
        ESP_LOGW("AgentNotify", "personal pending reject: clock_unsync");
#endif
        return false;
    }
    if (request.session == 0 || request.fetch_interval_ms == 0 || request.policy_expires_utc_ms == 0 ||
        request.http.port == 0 || request.http.coordinator_host.empty() ||
        request.http.coordinator_host.size() > 253 ||
        !printableField(request.http.device_id, NotificationController::max_id_bytes) ||
        !printableField(request.http.token, 512) ||
        !printableField(request.policy_version, NotificationController::max_id_bytes) ||
        request.http.limit < 1 || request.http.limit > 100) {
#ifdef ESP_PLATFORM
        ESP_LOGW("AgentNotify", "personal pending reject: bad_request");
#endif
        return false;
    }
    if (worker_active.test_and_set()) {
#ifdef ESP_PLATFORM
        ESP_LOGW("AgentNotify", "personal pending reject: worker_busy");
#endif
        return false;
    }
    // HTTPS 路徑必須帶 CA；cleartext 允許空 ca_pem。
    if (!request.http.coordinator_ca_pem.empty() &&
        (!request.http.coordinator_ca_pem.starts_with("-----BEGIN CERTIFICATE-----") ||
         request.http.coordinator_ca_pem.size() > 3999)) {
#ifdef ESP_PLATFORM
        ESP_LOGW("AgentNotify", "personal pending reject: bad_ca");
#endif
        worker_active.clear();
        return false;
    }
    auto* heap_request = new (std::nothrow) PersonalPendingWorkerRequest(std::move(request));
    if (!heap_request) {
#ifdef ESP_PLATFORM
        ESP_LOGW("AgentNotify", "personal pending reject: oom_request");
#endif
        worker_active.clear();
        return false;
    }
    BaseType_t created = static_cast<BaseType_t>(0);
#if defined(ESP_PLATFORM) && defined(CONFIG_SPIRAM) && CONFIG_SPIRAM
    // 內部 SRAM 緊張時改把 task stack 放 PSRAM（與 IMU 等既有路徑一致）。
    created = xTaskCreatePinnedToCoreWithCaps(runPersonalPendingWorker, "agent_pending", kWorkerStackBytes,
                                              heap_request, kWorkerPriority, nullptr, tskNO_AFFINITY,
                                              MALLOC_CAP_SPIRAM);
#else
    created = xTaskCreate(runPersonalPendingWorker, "agent_pending", kWorkerStackBytes, heap_request,
                          kWorkerPriority, nullptr);
#endif
    if (created != pdPASS) {
#ifdef ESP_PLATFORM
#if defined(CONFIG_SPIRAM) && CONFIG_SPIRAM
        ESP_LOGW("AgentNotify",
                 "personal pending reject: task_create_failed internal_free=%u largest=%u spiram_free=%u",
                 static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)),
                 static_cast<unsigned>(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)),
                 static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)));
#else
        ESP_LOGW("AgentNotify", "personal pending reject: task_create_failed");
#endif
#endif
        delete heap_request;
        worker_active.clear();
        return false;
    }
#ifdef ESP_PLATFORM
    ESP_LOGI("AgentNotify", "personal pending worker scheduled");
#endif
    return true;
}
#else
bool requestNotificationProductStream(std::uint64_t) { return false; }
void publishNotificationXiaozhiBusy(bool) noexcept {}
bool requestNotificationProductPairing(NotificationPairingEndpoint, std::uint16_t, std::uint64_t) { return false; }
NotificationPairingStatus notificationProductPairingStatus() { return {}; }
void cancelNotificationProductPairing() noexcept {}
bool requestPersonalPendingNotificationProduct(PersonalPendingWorkerRequest) { return false; }
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
