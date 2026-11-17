#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>
#include <stackchan/notifications/fail_closed_budget.h>
#include <stackchan/notifications/fail_closed_guard.h>
#include <stackchan/notifications/notification_controller.h>
#include <stackchan/notifications/notification_presenter.h>
#include <stackchan/notifications/presentation_receipt.h>
#include <stackchan/notifications/resource_arbiter.h>
#include <stackchan/notifications/runtime_limits.h>

using stackchan::notifications::FailClosedGuard;
using stackchan::notifications::LvglLockHooks;
using stackchan::notifications::LvglLockedUiPort;
using stackchan::notifications::NoticeKind;
using stackchan::notifications::NotificationController;
using stackchan::notifications::NotificationPresenter;
using stackchan::notifications::NotificationUiPort;
using stackchan::notifications::PresentationReceiptTracker;
using stackchan::notifications::ResourceArbiter;
using stackchan::notifications::kCoreS3MvpRuntimeProfile;
using stackchan::notifications::kMvpSoftWorstCaseRevokeMs;
using stackchan::notifications::kP004MaxUiUpdateGapMs;
using stackchan::notifications::mvpSoftWorstCaseRevokeMs;
using stackchan::notifications::softWorstCaseRevokeMs;
using State = NotificationController::State;

namespace {
void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

struct FakeUi final : NotificationUiPort {
    std::vector<std::string> ops;
    bool show(NoticeKind, std::string_view text) override
    {
        ops.push_back(std::string("show:") + std::string(text));
        return true;
    }
    void clear() override { ops.push_back("clear"); }
};

void lockFn(void*) {}
void unlockFn(void*) {}

void testBudgetConstants()
{
    expect(kP004MaxUiUpdateGapMs == 185, "P0-04 gap ceil(184054us)=185ms");
    expect(kMvpSoftWorstCaseRevokeMs == 4185, "MVP soft budget 4000+185");
    expect(mvpSoftWorstCaseRevokeMs() == 4185, "probe returns MVP budget");
    expect(softWorstCaseRevokeMs(kCoreS3MvpRuntimeProfile) == 4185, "profile helper matches");
}

void testHeartbeatSilenceRevokesWithinSoftBudget()
{
    // 使用 MVP heartbeat_timeout；短 stability 以便快速 Active。
    NotificationController controller({4, 4000, 5});
    ResourceArbiter arbiter;
    FakeUi inner;
    LvglLockedUiPort ui{inner, LvglLockHooks{lockFn, unlockFn, nullptr}};
    NotificationPresenter presenter{arbiter, ui};
    PresentationReceiptTracker receipts;
    FailClosedGuard guard{controller, presenter, &receipts};

    constexpr auto session = 1ULL;
    expect(controller.beginRecovery(session, "v1", 100'000, 0), "recovery");
    expect(controller.heartbeat(session, 5), "activate");
    expect(controller.state(5) == State::Active, "active");
    expect(!guard.poll(session, 5, 1000), "warm guard");
    expect(presenter.present(NoticeKind::Neutral, "private", 1), "show notice");
    expect(presenter.isVisible(), "visible before silence");

    const auto last_heartbeat = 5ULL;
    // 逾時前一毫秒：仍 Active，不得 Fail-Closed 清屏。
    const auto before_deadline = last_heartbeat + 4000 - 1;
    expect(controller.state(before_deadline) == State::Active, "still active just before timeout");
    expect(!guard.poll(session, before_deadline, 2000), "no revoke before heartbeat timeout");
    expect(presenter.isVisible(), "UI still visible before budget trigger");

    // 模擬最壞 poll 偏斜：剛好在 soft budget 邊界偵測。
    const auto revoke_at = last_heartbeat + kMvpSoftWorstCaseRevokeMs;
    expect(revoke_at - last_heartbeat == 4185, "elapsed equals soft budget");
    expect(guard.poll(session, revoke_at, 3000), "poll revokes at soft budget");
    expect(guard.lastInterrupted(), "interrupted");
    expect(!presenter.isVisible(), "cleared within soft budget");
    expect(controller.state(revoke_at) == State::Suspended, "suspended");
    expect(!inner.ops.empty() && inner.ops.back() == "clear", "ui clear");
}

void testTransportDisconnectFasterThanSoftBudget()
{
    NotificationController controller({4, 4000, 5});
    ResourceArbiter arbiter;
    FakeUi inner;
    LvglLockedUiPort ui{inner, LvglLockHooks{lockFn, unlockFn, nullptr}};
    NotificationPresenter presenter{arbiter, ui};
    FailClosedGuard guard{controller, presenter, nullptr};

    expect(controller.beginRecovery(1, "v1", 100'000, 0), "recovery");
    expect(controller.heartbeat(1, 5), "activate");
    expect(presenter.present(NoticeKind::Success, "ok", 1), "show");
    const auto last_heartbeat = 5ULL;
    const auto disconnect_at = last_heartbeat + 10;
    expect(guard.onTransportDisconnected(1, disconnect_at, 4000), "immediate transport revoke");
    expect(!presenter.isVisible(), "cleared");
    expect(disconnect_at - last_heartbeat < kMvpSoftWorstCaseRevokeMs, "transport path under soft budget");
}
}  // namespace

int main()
{
    testBudgetConstants();
    testHeartbeatSilenceRevokesWithinSoftBudget();
    testTransportDisconnectFasterThanSoftBudget();
}
