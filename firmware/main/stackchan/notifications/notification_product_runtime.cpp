#include "notification_product_runtime.h"

#include "device_stream_tls_client.h"
#include "fail_closed_guard.h"
#include "notification_credentials.h"
#include "notification_lvgl_hooks.h"
#include "notification_payload.h"
#include "notification_presenter.h"
#include "notification_product_loop.h"
#include "notification_utc_clock.h"
#include "presentation_receipt.h"
#include "resource_arbiter.h"
#include "runtime_limits.h"
#include "stream_bootstrap.h"
#include "stream_session_start.h"

#include <algorithm>
#include <array>
#include <mutex>
#include <utility>

namespace stackchan::notifications {
namespace {

struct NullNotificationUi final : NotificationUiPort {
    bool show(NoticeKind, std::string_view) override
    {
        // P2-08 前不畫 Avatar；回傳 true 僅表示埠可用，避免卡死佇列。
        return true;
    }
    void clear() override {}
};

struct ProductRuntime {
    NotificationRuntimeProfile profile = kCoreS3MvpRuntimeProfile;
    DeviceStreamTlsClient client{profile.controller, profile.max_frame_age_ms};
    ResourceArbiter arbiter;
    NullNotificationUi null_ui;
    LvglLockedUiPort ui{null_ui, makeHalLvglLockHooks()};
    NotificationPresenter presenter{arbiter, ui};
    PresentationReceiptTracker receipts;
    FailClosedGuard guard{client.controller(), presenter, &receipts};
    NotificationProductLoop loop{client.controller(), guard, presenter, &receipts};
    bool ready = false;
};

ProductRuntime& runtime()
{
    static ProductRuntime instance;
    return instance;
}

PendingNotificationCredentials& pendingCredentials()
{
    static PendingNotificationCredentials pending;
    return pending;
}

struct LocalPairing {
    std::mutex mutex;
    std::string id;
    NotificationPairingEndpoint endpoint;
    std::uint64_t started_at_utc_ms = 0;
    std::uint64_t expires_at_utc_ms = 0;
};

LocalPairing& localPairing()
{
    static LocalPairing pairing;
    return pairing;
}

bool hasDeviceScopes(JsonArrayConst scopes)
{
    constexpr std::array<std::string_view, 3> expected{"device:policy", "device:receipt", "device:stream"};
    return scopes.size() == expected.size() && std::ranges::all_of(expected, [&](std::string_view scope) {
        return std::any_of(scopes.begin(), scopes.end(), [&](JsonVariantConst value) {
            return payload::stringValue(value) == scope;
        });
    });
}

}  // namespace

void initNotificationProductRuntime()
{
    auto& rt = runtime();
    rt.ready = true;
    // 刻意不呼叫 start／fetch：缺憑證時保持 Fail-Closed Idle。
}

bool armNotificationProductRuntime(const StreamProvision& provision)
{
    auto& rt = runtime();
    const auto& profile = provision.profile;
    // The client already owns fixed controller and frame-age limits.
    if (!rt.ready || profile.controller.capacity != rt.profile.controller.capacity ||
        profile.controller.heartbeat_timeout_ms != rt.profile.controller.heartbeat_timeout_ms ||
        profile.controller.stability_ms != rt.profile.controller.stability_ms ||
        profile.max_frame_age_ms != rt.profile.max_frame_age_ms ||
        profile.max_frame_bytes != rt.profile.max_frame_bytes ||
        profile.network_timeout_ms != rt.profile.network_timeout_ms) {
        return false;
    }
    return armProvisionedDeviceStream(rt.client, provision);
}

bool beginNotificationProductPairing(std::string_view pairing_id, std::string_view challenge_expires_at,
                                     NotificationPairingEndpoint endpoint)
{
    const auto now = notificationUtcMs();
    const auto expires = payload::utcMillis(challenge_expires_at);
    constexpr std::uint64_t challenge_lifetime_ms = 10 * 60 * 1000;
    if (now == 0 || !expires || *expires <= now || *expires - now > challenge_lifetime_ms ||
        pairing_id.empty() || pairing_id.size() > NotificationController::max_id_bytes ||
        pairing_id.find('\0') != std::string_view::npos ||
        endpoint.coordinator_host.empty() || endpoint.coordinator_host.size() > 253 ||
        endpoint.port == 0 || endpoint.coordinator_ca_pem.empty() || endpoint.coordinator_ca_pem.size() > 3999) {
        return false;
    }
    auto& pairing = localPairing();
    const std::lock_guard lock(pairing.mutex);
    pendingCredentials().clear();
    pairing.id.assign(pairing_id);
    pairing.endpoint = std::move(endpoint);
    pairing.started_at_utc_ms = now;
    pairing.expires_at_utc_ms = *expires;
    return true;
}

bool finishNotificationProductPairing(std::string_view pairing_id, std::string_view response)
{
    auto& pairing = localPairing();
    const std::lock_guard lock(pairing.mutex);
    if (pairing.id.empty() || pairing.id != pairing_id) {
        return false;
    }
    pairing.id.clear();
    auto endpoint = std::exchange(pairing.endpoint, {});
    const auto now = notificationUtcMs();
    if (now < pairing.started_at_utc_ms || now >= pairing.expires_at_utc_ms ||
        response.empty() || response.size() > kCoreS3MvpRuntimeProfile.max_frame_bytes) {
        return false;
    }
    JsonDocument document;
    if (deserializeJson(document, response.data(), response.size(), DeserializationOption::NestingLimit(2))) {
        return false;
    }
    payload::CompactJsonMatch canonical(response);
    serializeJson(document, canonical);
    const auto result = document.as<JsonObjectConst>();
    if (!canonical.complete() || result.size() != 7 ||
        payload::stringValue(result["schema_version"]) != "0.1" ||
        payload::stringValue(result["pairing_id"]) != pairing_id ||
        payload::stringValue(result["subject_type"]) != "device" ||
        !hasDeviceScopes(result["scopes"].as<JsonArrayConst>())) {
        return false;
    }
    const auto expiry = payload::utcMillis(payload::stringValue(result["token_expires_at"]));
    const auto token = payload::stringValue(result["access_token"]);
    if (!expiry || token.size() < 16) {
        return false;
    }
    const auto before_stage = notificationUtcMs();
    if (before_stage < now || before_stage >= pairing.expires_at_utc_ms) {
        return false;
    }
    return pendingCredentials().stage(
        {{std::move(endpoint.coordinator_host), endpoint.port, std::move(endpoint.coordinator_ca_pem),
          std::string(token), std::string(payload::stringValue(result["subject_id"]))}, *expiry},
        before_stage);
}

void discardPendingNotificationProductCredentials()
{
    pendingCredentials().clear();
}

NotificationBootstrapResult fetchAndArmNotificationProductRuntime(std::uint64_t coordinator_generation)
{
    auto& rt = runtime();
    if (!rt.ready) {
        return NotificationBootstrapResult::NotInitialized;
    }
    if (rt.client.started()) {
        return NotificationBootstrapResult::AlreadyArmed;
    }
    const auto utc_ms = notificationUtcMs();
    if (utc_ms == 0) {
        return NotificationBootstrapResult::ClockUnsynchronized;
    }
    auto grant = pendingCredentials().take(utc_ms);
    if (!grant) {
        return NotificationBootstrapResult::CredentialsUnavailable;
    }

    StreamProvisionRequest request{};
    request.coordinator_host = std::move(grant->credentials.coordinator_host);
    request.port = grant->credentials.port;
    request.coordinator_ca_pem = std::move(grant->credentials.coordinator_ca_pem);
    request.token = std::move(grant->credentials.token);
    request.device_id = std::move(grant->credentials.device_id);
    request.generation = coordinator_generation;
    request.profile = rt.profile;
    request.now_utc_ms = utc_ms;

    PolicyLeaseHttpClient http;
    auto provision = fetchAndProvisionDeviceStream(http, request);
    if (!provision) {
        return NotificationBootstrapResult::PolicyUnavailable;
    }
    const auto before_upgrade_utc_ms = notificationUtcMs();
    if (before_upgrade_utc_ms < utc_ms || before_upgrade_utc_ms >= grant->expires_at_utc_ms) {
        return NotificationBootstrapResult::CredentialsUnavailable;
    }
    provision->config.policy_expires_utc_ms =
        std::min(provision->config.policy_expires_utc_ms, grant->expires_at_utc_ms);
    return armNotificationProductRuntime(*provision) ? NotificationBootstrapResult::Upgraded
                                                     : NotificationBootstrapResult::StreamUpgradeFailed;
}

bool isNotificationProductStreamArmed()
{
    auto& rt = runtime();
    return rt.ready && rt.client.started();
}

void tickNotificationProductRuntime(std::uint64_t now_ms, std::uint64_t utc_ms, bool xiaozhi_busy)
{
    auto& rt = runtime();
    if (!rt.ready) {
        return;
    }
    const auto activity =
        xiaozhi_busy ? ResourceArbiter::XiaozhiActivity::Busy : ResourceArbiter::XiaozhiActivity::Idle;
    rt.presenter.onXiaozhiActivity(activity, now_ms);
    // read_timeout_ms=0：不在 update task 內阻塞等待 socket。
    (void)notificationProductLoopPollClient(rt.loop, rt.client, now_ms, utc_ms, 0);
}

}  // namespace stackchan::notifications
