#include "notification_product_runtime.h"

#include "device_stream_tls_client.h"
#include "fail_closed_guard.h"
#include "notification_credentials.h"
#include "notification_lvgl_hooks.h"
#include "notification_presenter.h"
#include "notification_product_loop.h"
#include "notification_utc_clock.h"
#include "presentation_receipt.h"
#include "resource_arbiter.h"
#include "runtime_limits.h"
#include "stream_bootstrap.h"
#include "stream_session_start.h"

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
    auto credentials = loadNotificationCredentials();
    if (!credentials) {
        return NotificationBootstrapResult::CredentialsUnavailable;
    }

    StreamProvisionRequest request{};
    request.coordinator_host = std::move(credentials->coordinator_host);
    request.port = credentials->port;
    request.coordinator_ca_pem = std::move(credentials->coordinator_ca_pem);
    request.token = std::move(credentials->token);
    request.device_id = std::move(credentials->device_id);
    request.generation = coordinator_generation;
    request.profile = rt.profile;
    request.now_utc_ms = utc_ms;

    PolicyLeaseHttpClient http;
    const auto provision = fetchAndProvisionDeviceStream(http, request);
    if (!provision) {
        return NotificationBootstrapResult::PolicyUnavailable;
    }
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
