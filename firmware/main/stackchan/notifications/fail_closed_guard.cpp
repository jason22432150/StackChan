#include "fail_closed_guard.h"

namespace stackchan::notifications {

FailClosedGuard::FailClosedGuard(NotificationController& controller, NotificationPresenter& presenter,
                                 PresentationReceiptTracker* receipts)
    : _controller(controller), _presenter(presenter), _receipts(receipts)
{
}

bool FailClosedGuard::interruptVisible(Tick now, UtcMs reported_at_utc_ms, std::string_view receipt_id,
                                       std::string_view reason)
{
    if (!_presenter.isVisible()) {
        _last_interrupted = false;
        return false;
    }
    // 先同步撤銷授權並清屏；不等待子系統 ACK（不變式 #2）。
    _presenter.interrupt(now);
    if (_receipts != nullptr) {
        const auto status = _receipts->status();
        if (status == PresentationReceiptTracker::Status::Accepted ||
            status == PresentationReceiptTracker::Status::Started) {
            (void)_receipts->interrupt(receipt_id, reported_at_utc_ms, reason);
        }
    }
    _last_interrupted = true;
    return true;
}

bool FailClosedGuard::poll(SessionId session, Tick now, UtcMs reported_at_utc_ms)
{
    (void)session;
    const auto state = _controller.state(now);
    const bool dropped = (_last_state == NotificationController::State::Active ||
                          _last_state == NotificationController::State::Recovering) &&
                         state == NotificationController::State::Suspended;
    _last_state = state;
    if (!dropped) {
        _last_interrupted = false;
        return false;
    }
    return interruptVisible(now, reported_at_utc_ms, "rcp-failclosed", "coordinator.disconnected");
}

bool FailClosedGuard::onTransportDisconnected(SessionId session, Tick now, UtcMs reported_at_utc_ms,
                                              std::string_view interrupt_receipt_id)
{
    _controller.suspend(session);
    _last_state = _controller.state(now);
    return interruptVisible(now, reported_at_utc_ms, interrupt_receipt_id, "transport.disconnected");
}

bool failClosedGuardPollProbe(FailClosedGuard& guard, FailClosedGuard::SessionId session,
                              FailClosedGuard::Tick now, FailClosedGuard::UtcMs reported_at_utc_ms)
{
    return guard.poll(session, now, reported_at_utc_ms);
}

}  // namespace stackchan::notifications
