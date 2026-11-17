#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>
#include <stackchan/notifications/fail_closed_guard.h>
#include <stackchan/notifications/notification_controller.h>
#include <stackchan/notifications/notification_presenter.h>
#include <stackchan/notifications/presentation_receipt.h>
#include <stackchan/notifications/resource_arbiter.h>

using stackchan::notifications::FailClosedGuard;
using stackchan::notifications::LvglLockHooks;
using stackchan::notifications::LvglLockedUiPort;
using stackchan::notifications::NoticeKind;
using stackchan::notifications::NotificationController;
using stackchan::notifications::NotificationPresenter;
using stackchan::notifications::NotificationUiPort;
using stackchan::notifications::PresentationReceiptTracker;
using stackchan::notifications::ResourceArbiter;
using State = NotificationController::State;
using ReceiptStatus = PresentationReceiptTracker::Status;

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

struct Fixture {
    NotificationController controller{{2, 10, 1}};
    ResourceArbiter arbiter;
    FakeUi inner;
    LvglLockedUiPort ui{inner, LvglLockHooks{lockFn, unlockFn, nullptr}};
    NotificationPresenter presenter{arbiter, ui};
    PresentationReceiptTracker receipts;
    FailClosedGuard guard{controller, presenter, &receipts};

    void activate(NotificationController::SessionId session = 1)
    {
        expect(controller.beginRecovery(session, "policy", 1000, 0), "recovery");
        expect(controller.heartbeat(session, 1), "stable");
        expect(controller.state(1) == State::Active, "active");
        // warm guard last_state
        expect(!guard.poll(session, 1, 1000), "no drop yet");
    }

    void showNotice()
    {
        expect(presenter.present(NoticeKind::Neutral, "secret note", 2), "present");
        expect(receipts.accept("rcp-a", "dlv-1", "att-1", "cores3", 1, 2000).outcome ==
                   PresentationReceiptTracker::Outcome::Ok,
               "accept receipt");
        expect(receipts.start("rcp-s", 2100).outcome == PresentationReceiptTracker::Outcome::Ok,
               "start receipt");
        expect(presenter.isVisible(), "visible");
    }
};

void testHeartbeatTimeoutClearsPresentationAndReceipt()
{
    Fixture fx;
    fx.activate();
    fx.showNotice();
    // heartbeat_timeout_ms=10；last heartbeat at 1 → at now=12 suspends
    expect(fx.guard.poll(1, 12, 12000), "poll detects disconnect");
    expect(fx.guard.lastInterrupted(), "interrupted flag");
    expect(!fx.presenter.isVisible(), "cleared");
    expect(fx.controller.state(12) == State::Suspended, "controller suspended");
    expect(fx.receipts.status() == ReceiptStatus::Interrupted, "interrupted receipt");
    expect(!fx.inner.ops.empty() && fx.inner.ops.back() == "clear", "ui clear");
}

void testTransportDisconnectSuspendsEvenIfStillActive()
{
    Fixture fx;
    fx.activate();
    fx.showNotice();
    expect(fx.guard.onTransportDisconnected(1, 5, 5000, "rcp-disc"), "transport disconnect");
    expect(!fx.presenter.isVisible(), "cleared on transport drop");
    expect(fx.controller.state(5) == State::Suspended, "suspended by transport");
    expect(fx.receipts.status() == ReceiptStatus::Interrupted, "receipt interrupted");
}

void testNoPresentationMeansNoInterruptSideEffect()
{
    Fixture fx;
    fx.activate();
    expect(!fx.guard.poll(1, 12, 12000), "drop without visible presentation");
    expect(!fx.guard.lastInterrupted(), "no interrupt");
    expect(fx.receipts.status() == ReceiptStatus::None, "no receipt churn");
}

void testDoesNotTouchXiaozhiSurface()
{
    // 編譯期隔離：本測試翻譯單元不 include Xiaozhi／Audio／Servo 標頭。
    // 行為上 FailClosedGuard 僅清通知 UI；此處再確認 interrupt 後可再次 present（授權重開）。
    Fixture fx;
    fx.activate(1);
    fx.showNotice();
    expect(fx.guard.onTransportDisconnected(1, 5, 5000), "disconnect");
    expect(fx.controller.beginRecovery(2, "policy", 2000, 20), "new session");
    expect(fx.controller.heartbeat(2, 21), "restabilize");
    expect(fx.guard.poll(2, 21, 21000) == false, "no false interrupt");
    expect(fx.presenter.present(NoticeKind::Success, "after reconnect", 22), "present after recover");
}
}  // namespace

int main()
{
    testHeartbeatTimeoutClearsPresentationAndReceipt();
    testTransportDisconnectSuspendsEvenIfStillActive();
    testNoPresentationMeansNoInterruptSideEffect();
    testDoesNotTouchXiaozhiSurface();
    return 0;
}
