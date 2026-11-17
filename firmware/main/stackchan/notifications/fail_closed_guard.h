#pragma once

#include "notification_controller.h"
#include "notification_presenter.h"
#include "presentation_receipt.h"

#include <string_view>

namespace stackchan::notifications {

/**
 * P2-08 軟路徑：Coordinator 失聯／Suspend 時 Fail-Closed 中斷已呈現內容。
 *
 * 單一執行上下文。不呼叫 Xiaozhi／AudioCodec／Servo；只協調
 * NotificationController → NotificationPresenter → PresentationReceiptTracker。
 * 實機 Gate G3／R-006 量測不在本模組範圍。
 */
class FailClosedGuard {
public:
    using Tick = NotificationController::Tick;
    using SessionId = NotificationController::SessionId;
    using UtcMs = PresentationReceiptTracker::UtcMs;

    FailClosedGuard(NotificationController& controller, NotificationPresenter& presenter,
                    PresentationReceiptTracker* receipts = nullptr);

    /**
     * 每個控制迴圈呼叫：讀取 controller.state(now)。
     * 若自 Active／Recovering 落入 Suspended，且 presenter 可見 → interrupt＋interrupted 收據。
     */
    bool poll(SessionId session, Tick now, UtcMs reported_at_utc_ms);

    /**
     * Transport 顯式斷線：先 controller.suspend，再清屏／收據（若仍可見）。
     * 回傳是否執行了呈現中斷。
     */
    bool onTransportDisconnected(SessionId session, Tick now, UtcMs reported_at_utc_ms,
                                 std::string_view interrupt_receipt_id = "rcp-disconnect");

    bool lastInterrupted() const { return _last_interrupted; }
    NotificationController::State lastState() const { return _last_state; }

private:
    bool interruptVisible(Tick now, UtcMs reported_at_utc_ms, std::string_view receipt_id,
                          std::string_view reason);

    NotificationController& _controller;
    NotificationPresenter& _presenter;
    PresentationReceiptTracker* _receipts;
    NotificationController::State _last_state = NotificationController::State::Suspended;
    bool _last_interrupted = false;
};

/** link_anchor 保留用。 */
bool failClosedGuardPollProbe(FailClosedGuard& guard, FailClosedGuard::SessionId session,
                              FailClosedGuard::Tick now, FailClosedGuard::UtcMs reported_at_utc_ms);

}  // namespace stackchan::notifications
