#pragma once

#include "fail_closed_guard.h"
#include "notification_controller.h"
#include "notification_presenter.h"
#include "presentation_receipt.h"

#include <cstdint>

namespace stackchan::notifications {

class DeviceStreamTlsClient;

/**
 * P2-04 產品路徑：常駐控制迴圈的單一 tick 進入點。
 *
 * 組裝 NotificationController＋FailClosedGuard＋NotificationPresenter。
 * 單一執行上下文；不持 LVGL lock；不呼叫 Xiaozhi／Audio／Servo；不自行開啟 TLS。
 * TLS 須由呼叫端先 `startProvisionedDeviceStream`；未 start 時 pollClient 為 no-op。
 * Avatar／ShowNotification 實機畫面屬 P2-08，不在本模組完成。
 */
class NotificationProductLoop {
public:
    using Tick = NotificationController::Tick;
    using SessionId = NotificationController::SessionId;
    using UtcMs = PresentationReceiptTracker::UtcMs;

    enum class Outcome : std::uint8_t {
        Idle = 0,
        Presented = 1,
        Interrupted = 2,
        StreamDead = 3,
    };

    NotificationProductLoop(NotificationController& controller, FailClosedGuard& guard,
                            NotificationPresenter& presenter,
                            PresentationReceiptTracker* receipts = nullptr);

    void attachSession(SessionId session);
    void clearSession();
    SessionId session() const { return _session; }
    bool hasSession() const { return _session != 0; }

    /**
     * 每個控制迴圈呼叫：FailClosedGuard.poll →（Active 且尚無可見通知）takeNext → present。
     * MVP 呈現文字為 delivery id（完整 intent 文案屬後續契約擴充）。
     */
    Outcome tick(Tick now, UtcMs reported_at_utc_ms);

    /** Transport 顯式斷線：suspend＋清屏。 */
    bool onTransportDisconnected(Tick now, UtcMs reported_at_utc_ms);

    bool isPresenting() const { return _presenter.isVisible(); }

private:
    NotificationController& _controller;
    FailClosedGuard& _guard;
    NotificationPresenter& _presenter;
    PresentationReceiptTracker* _receipts;
    SessionId _session = 0;
};

/**
 * 若 client 已 start：attach session → poll；失敗則 onTransportDisconnected（StreamDead）。
 * 成功則 tick。未 start 時回傳 Idle（不開啟 TLS）。
 */
NotificationProductLoop::Outcome notificationProductLoopPollClient(
    NotificationProductLoop& loop, DeviceStreamTlsClient& client, NotificationProductLoop::Tick now,
    NotificationProductLoop::UtcMs reported_at_utc_ms, int read_timeout_ms = 0);

/** link_anchor 保留用。 */
bool notificationProductLoopLinked();

}  // namespace stackchan::notifications
