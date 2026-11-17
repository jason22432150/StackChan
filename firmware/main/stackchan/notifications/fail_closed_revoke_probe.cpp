#include "fail_closed_revoke_probe.h"

namespace stackchan::notifications {

FailClosedRevokeProbe::FailClosedRevokeProbe(NotificationUiPort& ui, LvglLockHooks locks,
                                             NotificationController::Limits limits, Tick budget_ms)
    : _controller(limits),
      _ui(ui, locks),
      _presenter(_arbiter, _ui),
      _guard(_controller, _presenter, &_receipts),
      _budget_ms(budget_ms)
{
}

bool FailClosedRevokeProbe::poll(Tick now_ms)
{
    if (_phase == Phase::Done) {
        return false;
    }

    constexpr auto session = 1ULL;

    if (_phase == Phase::Arm) {
        if (_controller.state(now_ms) == NotificationController::State::Suspended) {
            // policy 給足夠長的租約，避免量測期間誤到期。
            if (!_controller.beginRecovery(session, "r006", now_ms + 3'600'000, now_ms)) {
                return false;
            }
            (void)_controller.heartbeat(session, now_ms);
            (void)_guard.poll(session, now_ms, now_ms);
            return false;
        }
        // 穩定門檻內持續心跳；Active 後記錄最後心跳並停止續跳。
        (void)_controller.heartbeat(session, now_ms);
        if (_controller.state(now_ms) != NotificationController::State::Active) {
            return false;
        }
        _last_heartbeat_ms = now_ms;
        (void)_guard.poll(session, now_ms, now_ms);
        _phase = Phase::Show;
        return false;
    }

    if (_phase == Phase::Show) {
        if (!_presenter.present(NoticeKind::Neutral, "r006-probe", 1)) {
            return false;
        }
        (void)_receipts.accept("rcp-r006-a", "dlv-r006", "att-r006", "cores3", 1, now_ms);
        (void)_receipts.start("rcp-r006-s", now_ms + 1);
        _phase = Phase::WaitSilence;
        return false;
    }

    // WaitSilence：不再送 heartbeat；依真實迴圈節奏 poll，直到逾時撤銷。
    if (!_guard.poll(session, now_ms, now_ms)) {
        return false;
    }

    FailClosedRevokeSample sample{};
    sample.last_heartbeat_ms = _last_heartbeat_ms;
    sample.revoked_at_ms = now_ms;
    sample.revoke_ms = now_ms >= _last_heartbeat_ms ? now_ms - _last_heartbeat_ms : 0;
    sample.budget_ms = _budget_ms;
    sample.interrupted = _guard.lastInterrupted();
    sample.within_budget = sample.interrupted && sample.revoke_ms <= _budget_ms && !_presenter.isVisible();
    _sample = sample;
    _phase = Phase::Done;
    return true;
}

bool failClosedRevokeProbeLinked()
{
    return true;
}

}  // namespace stackchan::notifications
