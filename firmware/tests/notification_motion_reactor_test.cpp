#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

#include <stackchan/notifications/notification_motion_reactor.h>
#include <stackchan/notifications/notification_presenter.h>
#include <stackchan/notifications/resource_arbiter.h>

using stackchan::notifications::LvglLockHooks;
using stackchan::notifications::LvglLockedUiPort;
using stackchan::notifications::NoticeKind;
using stackchan::notifications::NoticeMotionCommand;
using stackchan::notifications::NoticeMotionSink;
using stackchan::notifications::NotificationMotionReactor;
using stackchan::notifications::NotificationPresenter;
using stackchan::notifications::NotificationUiPort;
using stackchan::notifications::ResourceArbiter;
using XiaozhiActivity = ResourceArbiter::XiaozhiActivity;

namespace {

void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

struct Capture {
    std::vector<std::string> ops;
    int last_yaw = 0;
};

bool captureNudge(void* ctx, const NoticeMotionCommand& cmd)
{
    auto* cap = static_cast<Capture*>(ctx);
    cap->last_yaw = cmd.yaw;
    cap->ops.push_back("nudge");
    return true;
}

void captureHome(void* ctx, const NoticeMotionCommand& cmd)
{
    auto* cap = static_cast<Capture*>(ctx);
    cap->last_yaw = cmd.yaw;
    cap->ops.push_back("home");
}

struct FakeUi final : NotificationUiPort {
    bool show(NoticeKind, std::string_view) override { return true; }
    void clear() override {}
};

void lockFn(void*) {}
void unlockFn(void*) {}

void testStartRequiresMotionLease()
{
    ResourceArbiter arbiter;
    Capture cap;
    NotificationMotionReactor reactor{NoticeMotionSink{captureNudge, captureHome, &cap}};
    const auto gen = arbiter.beginPresentation(1);
    expect(reactor.start(arbiter, gen, NoticeKind::Neutral, 1), "start");
    expect(reactor.isActive(), "active");
    expect(arbiter.hasLease(ResourceArbiter::Resource::Motion), "motion lease");
    expect(!cap.ops.empty() && cap.ops.back() == "nudge", "nudge called");
    expect(cap.last_yaw < 0, "neutral yaw negative");
}

void testXiaozhiBusyBlocksStart()
{
    ResourceArbiter arbiter;
    Capture cap;
    NotificationMotionReactor reactor{NoticeMotionSink{captureNudge, captureHome, &cap}};
    arbiter.onXiaozhiActivity(XiaozhiActivity::Busy, 1);
    const auto gen = arbiter.beginPresentation(1);
    expect(!reactor.start(arbiter, gen, NoticeKind::Success, 1), "busy blocks");
    expect(cap.ops.empty(), "no nudge");
}

void testForceStopOnInterruptViaPresenter()
{
    ResourceArbiter arbiter;
    FakeUi inner;
    LvglLockedUiPort ui{inner, LvglLockHooks{lockFn, unlockFn, nullptr}};
    Capture cap;
    NotificationMotionReactor reactor{NoticeMotionSink{captureNudge, captureHome, &cap}};
    NotificationPresenter presenter{arbiter, ui, &reactor};

    expect(presenter.present(NoticeKind::Success, "Agent done: x", 1), "present");
    expect(reactor.isActive(), "motion active");
    expect(arbiter.hasLease(ResourceArbiter::Resource::Motion), "leased");

    (void)presenter.interrupt(2);
    expect(!reactor.isActive(), "stopped");
    expect(!cap.ops.empty() && cap.ops.back() == "home", "homed on interrupt");
    expect(!arbiter.hasLease(ResourceArbiter::Resource::Motion), "lease cleared");
}

void testBusyStopsActiveMotion()
{
    ResourceArbiter arbiter;
    FakeUi inner;
    LvglLockedUiPort ui{inner, LvglLockHooks{lockFn, unlockFn, nullptr}};
    Capture cap;
    NotificationMotionReactor reactor{NoticeMotionSink{captureNudge, captureHome, &cap}};
    NotificationPresenter presenter{arbiter, ui, &reactor};

    expect(presenter.present(NoticeKind::Neutral, "Agent update: y", 1), "present");
    presenter.onXiaozhiActivity(XiaozhiActivity::Busy, 2);
    expect(!reactor.isActive(), "stopped on busy");
    expect(!cap.ops.empty() && cap.ops.back() == "home", "homed on busy");
}

}  // namespace

int main()
{
    testStartRequiresMotionLease();
    testXiaozhiBusyBlocksStart();
    testForceStopOnInterruptViaPresenter();
    testBusyStopsActiveMotion();
    return 0;
}
