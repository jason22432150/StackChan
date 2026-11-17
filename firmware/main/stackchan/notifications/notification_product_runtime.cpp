#include "notification_product_runtime.h"

#include "device_stream_tls_client.h"
#include "fail_closed_guard.h"
#include "notification_lvgl_hooks.h"
#include "notification_presenter.h"
#include "notification_product_loop.h"
#include "presentation_receipt.h"
#include "resource_arbiter.h"
#include "runtime_limits.h"

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
