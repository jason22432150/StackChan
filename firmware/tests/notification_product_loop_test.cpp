#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>
#include <stackchan/notifications/device_stream_ingress.h>
#include <stackchan/notifications/fail_closed_guard.h>
#include <stackchan/notifications/notification_controller.h>
#include <stackchan/notifications/notification_presenter.h>
#include <stackchan/notifications/notification_product_loop.h>
#include <stackchan/notifications/presentation_receipt.h>
#include <stackchan/notifications/resource_arbiter.h>

using stackchan::notifications::DeviceStreamIngress;
using stackchan::notifications::FailClosedGuard;
using stackchan::notifications::LvglLockHooks;
using stackchan::notifications::LvglLockedUiPort;
using stackchan::notifications::NoticeKind;
using stackchan::notifications::NotificationController;
using stackchan::notifications::NotificationPresenter;
using stackchan::notifications::NotificationProductLoop;
using stackchan::notifications::NotificationUiPort;
using stackchan::notifications::PresentationReceiptTracker;
using stackchan::notifications::ResourceArbiter;
using Outcome = NotificationProductLoop::Outcome;
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

struct Fixture {
    NotificationController controller{{2, 10, 1}};
    DeviceStreamIngress ingress{controller, 5};
    ResourceArbiter arbiter;
    FakeUi inner;
    LvglLockedUiPort ui{inner, LvglLockHooks{lockFn, unlockFn, nullptr}};
    NotificationPresenter presenter{arbiter, ui};
    PresentationReceiptTracker receipts;
    FailClosedGuard guard{controller, presenter, &receipts};
    NotificationProductLoop loop{controller, guard, presenter, &receipts};

    void activate(NotificationController::SessionId session = 1)
    {
        // 可信 UTC 錨：bound_utc=1000＠now=0；之後 estimated_utc = 1000 + now。
        expect(ingress.bindVerified({session, "dev", "v1", 1, 10'000}, 1000, 0), "bind");
        expect(ingress.receiveHeartbeat({session, "dev", "v1", 1, 1001}, 1), "stable hb");
        expect(controller.state(1) == State::Active, "active");
        loop.attachSession(session);
        expect(loop.tick(1, 1001) == Outcome::Idle, "warm guard without drop");
    }
};

void testIdleWithoutSession()
{
    Fixture fx;
    expect(fx.loop.tick(1, 1000) == Outcome::Idle, "no session is idle");
    expect(!fx.loop.isPresenting(), "not presenting");
}

void testPresentDequeuesOneDelivery()
{
    Fixture fx;
    fx.activate();
    expect(fx.ingress.receiveIntent({1, "dev", "v1", 1, 1002}, "dlv-1", 2000, 2), "enqueue");
    expect(fx.loop.tick(2, 1002) == Outcome::Presented, "present delivery");
    expect(fx.presenter.isVisible(), "visible");
    expect(!fx.inner.ops.empty() && fx.inner.ops.back() == "show:Agent update: dlv-1",
           "ui show basic notice text");
    expect(fx.receipts.status() == PresentationReceiptTracker::Status::Started, "receipt started");
    // 可見期間不再 dequeue／覆蓋
    expect(fx.ingress.receiveIntent({1, "dev", "v1", 1, 1003}, "dlv-2", 2000, 3), "second intent");
    expect(fx.loop.tick(3, 1003) == Outcome::Idle, "hold while visible");
}

void testFailClosedInterruptOnHeartbeatTimeout()
{
    Fixture fx;
    fx.activate();
    expect(fx.ingress.receiveIntent({1, "dev", "v1", 1, 1002}, "dlv-x", 2000, 2), "enqueue");
    expect(fx.loop.tick(2, 1002) == Outcome::Presented, "present");
    // heartbeat_timeout_ms=10；last hb at 1 → now=12 Suspended
    expect(fx.loop.tick(12, 12'000) == Outcome::Interrupted, "fail-closed interrupt");
    expect(!fx.presenter.isVisible(), "cleared");
    expect(fx.receipts.status() == PresentationReceiptTracker::Status::Interrupted, "interrupted receipt");
}

void testTransportDisconnectClearsSession()
{
    Fixture fx;
    fx.activate();
    expect(fx.ingress.receiveIntent({1, "dev", "v1", 1, 1002}, "dlv-y", 2000, 2), "enqueue");
    expect(fx.loop.tick(2, 1002) == Outcome::Presented, "present");
    expect(fx.loop.onTransportDisconnected(5, 5000), "transport drop");
    expect(!fx.loop.hasSession(), "session cleared");
    expect(!fx.presenter.isVisible(), "cleared");
    expect(fx.controller.state(5) == State::Suspended, "suspended");
}

void testXiaozhiBusyBlocksPresent()
{
    Fixture fx;
    fx.activate();
    fx.presenter.onXiaozhiActivity(ResourceArbiter::XiaozhiActivity::Busy, 2);
    expect(fx.ingress.receiveIntent({1, "dev", "v1", 1, 1002}, "dlv-busy", 2000, 2), "enqueue");
    expect(fx.loop.tick(2, 1002) == Outcome::Idle, "busy rejects present");
    expect(!fx.presenter.isVisible(), "not visible under busy");
}

void testXiaozhiBusyPreemptsVisibleNotice()
{
    Fixture fx;
    fx.activate();
    expect(fx.ingress.receiveIntent({1, "dev", "v1", 1, 1002}, "dlv-vis", 2000, 2), "enqueue");
    expect(fx.loop.tick(2, 1002) == Outcome::Presented, "presented");
    expect(fx.presenter.isVisible(), "visible");
    // 對話開始：清屏；佇列中下一則在 Busy 期間不得 present。
    fx.presenter.onXiaozhiActivity(ResourceArbiter::XiaozhiActivity::Busy, 3);
    expect(!fx.presenter.isVisible(), "preempted");
    expect(fx.ingress.receiveIntent({1, "dev", "v1", 1, 1003}, "dlv-wait", 2000, 3), "queued");
    expect(fx.loop.tick(3, 1003) == Outcome::Idle, "busy holds queue");
    expect(!fx.presenter.isVisible(), "still not visible");
}

void testLinkedAnchorProbe()
{
    expect(stackchan::notifications::notificationProductLoopLinked(), "link retain probe");
}
}  // namespace

int main()
{
    testIdleWithoutSession();
    testPresentDequeuesOneDelivery();
    testFailClosedInterruptOnHeartbeatTimeout();
    testTransportDisconnectClearsSession();
    testXiaozhiBusyBlocksPresent();
    testXiaozhiBusyPreemptsVisibleNotice();
    testLinkedAnchorProbe();
    return 0;
}
