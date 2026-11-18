#include "notification_product_loop.h"

#include "basic_notice_text.h"

namespace stackchan::notifications {

NotificationProductLoop::NotificationProductLoop(NotificationController& controller, FailClosedGuard& guard,
                                                 NotificationPresenter& presenter,
                                                 PresentationReceiptTracker* receipts)
    : _controller(controller), _guard(guard), _presenter(presenter), _receipts(receipts)
{
}

void NotificationProductLoop::attachSession(SessionId session)
{
    _session = session;
}

void NotificationProductLoop::clearSession()
{
    _session = 0;
}

NotificationProductLoop::Outcome NotificationProductLoop::tick(Tick now, UtcMs reported_at_utc_ms)
{
    if (_session == 0) {
        return Outcome::Idle;
    }
    if (_guard.poll(_session, now, reported_at_utc_ms)) {
        return Outcome::Interrupted;
    }
    if (_controller.state(now) != NotificationController::State::Active) {
        return Outcome::Idle;
    }
    // MVP：同一時間只呈現一則；可見期間不 dequeue，避免覆蓋。
    if (_presenter.isVisible()) {
        return Outcome::Idle;
    }
    auto next = _controller.takeNext(_session, now);
    if (!next) {
        return Outcome::Idle;
    }
    const std::string_view delivery{next->id.data()};
    // 個人版基本提示：中性樣式＋可讀文案；不宣稱 task.succeeded。
    char notice[NotificationPresenter::max_text_bytes + 1] = {};
    const auto notice_len =
        formatBasicNoticeText(NoticeKind::Neutral, delivery, notice, sizeof(notice));
    if (notice_len == 0 ||
        !_presenter.present(NoticeKind::Neutral, std::string_view(notice, notice_len), now)) {
        return Outcome::Idle;
    }
    if (_receipts != nullptr) {
        // 收據 ID 以 delivery 派生，長度受 max_id_bytes 約束。
        char accept_id[PresentationReceiptTracker::max_id_bytes + 1] = {};
        char start_id[PresentationReceiptTracker::max_id_bytes + 1] = {};
        const auto n = delivery.size();
        constexpr std::size_t prefix = 6;
        const auto copy_n =
            n + prefix < sizeof(accept_id) ? n : sizeof(accept_id) - prefix - 1;
        accept_id[0] = 'r';
        accept_id[1] = 'c';
        accept_id[2] = 'p';
        accept_id[3] = '-';
        accept_id[4] = 'a';
        accept_id[5] = ':';
        for (std::size_t i = 0; i < copy_n; ++i) {
            accept_id[prefix + i] = delivery[i];
        }
        start_id[0] = 'r';
        start_id[1] = 'c';
        start_id[2] = 'p';
        start_id[3] = '-';
        start_id[4] = 's';
        start_id[5] = ':';
        for (std::size_t i = 0; i < copy_n; ++i) {
            start_id[prefix + i] = delivery[i];
        }
        (void)_receipts->accept(accept_id, delivery, "att-mvp", "cores3", _presenter.generation(),
                                reported_at_utc_ms);
        (void)_receipts->start(start_id, reported_at_utc_ms);
    }
    return Outcome::Presented;
}

bool NotificationProductLoop::onTransportDisconnected(Tick now, UtcMs reported_at_utc_ms)
{
    if (_session == 0) {
        return false;
    }
    const bool interrupted = _guard.onTransportDisconnected(_session, now, reported_at_utc_ms);
    clearSession();
    return interrupted;
}

bool notificationProductLoopLinked()
{
    return true;
}

}  // namespace stackchan::notifications
