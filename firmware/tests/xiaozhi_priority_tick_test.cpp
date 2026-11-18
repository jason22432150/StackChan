#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

#include <stackchan/notifications/notification_motion_reactor.h>
#include <stackchan/notifications/notification_presenter.h>
#include <stackchan/notifications/resource_arbiter.h>
#include <stackchan/notifications/xiaozhi_priority_tick.h>

using stackchan::notifications::LvglLockHooks;
using stackchan::notifications::LvglLockedUiPort;
using stackchan::notifications::NoticeKind;
using stackchan::notifications::NoticeMotionCommand;
using stackchan::notifications::NoticeMotionSink;
using stackchan::notifications::NotificationMotionReactor;
using stackchan::notifications::NotificationPresenter;
using stackchan::notifications::NotificationUiPort;
using stackchan::notifications::ResourceArbiter;
using stackchan::notifications::applyXiaozhiPriorityTick;
using stackchan::notifications::xiaozhiPriorityBlocksPresent;

namespace {

void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

struct CaptureUi final : NotificationUiPort {
    std::vector<std::string> ops;
    bool show(NoticeKind, std::string_view text) override
    {
        ops.push_back(std::string("show:") + std::string(text));
        return true;
    }
    void clear() override { ops.push_back("clear"); }
};

struct CaptureMotion {
    std::vector<std::string> ops;
};

bool motionNudge(void* ctx, const NoticeMotionCommand&)
{
    static_cast<CaptureMotion*>(ctx)->ops.push_back("nudge");
    return true;
}

void motionHome(void* ctx, const NoticeMotionCommand&)
{
    static_cast<CaptureMotion*>(ctx)->ops.push_back("home");
}

void lockFn(void*) {}
void unlockFn(void*) {}

struct Fixture {
    ResourceArbiter arbiter;
    CaptureUi inner;
    LvglLockedUiPort ui{inner, LvglLockHooks{lockFn, unlockFn, nullptr}};
    CaptureMotion motion_cap;
    NotificationMotionReactor motion{NoticeMotionSink{motionNudge, motionHome, &motion_cap}};
    NotificationPresenter presenter{arbiter, ui, &motion};
};

void testBusyPreemptsVisibleNoticeAndMotion()
{
    Fixture fx;
    expect(fx.presenter.present(NoticeKind::Neutral, "Agent update: a", 1), "present");
    expect(fx.presenter.isVisible(), "visible");
    expect(fx.motion.isActive(), "motion active");
    expect(!xiaozhiPriorityBlocksPresent(fx.arbiter), "idle allows");

    // 模擬 tickNotificationProductRuntime(..., xiaozhi_busy=true) 的優先步驟。
    applyXiaozhiPriorityTick(fx.presenter, true, 2);
    expect(xiaozhiPriorityBlocksPresent(fx.arbiter), "busy blocks");
    expect(!fx.presenter.isVisible(), "cleared");
    expect(!fx.motion.isActive(), "motion stopped");
    expect(!fx.inner.ops.empty() && fx.inner.ops.back() == "clear", "ui clear");
    expect(!fx.motion_cap.ops.empty() && fx.motion_cap.ops.back() == "home", "servo home");

    // Busy 期間不得新 present。
    expect(!fx.presenter.present(NoticeKind::Success, "Agent done: b", 3), "busy rejects");
}

void testIdleAllowsPresentAgain()
{
    Fixture fx;
    applyXiaozhiPriorityTick(fx.presenter, true, 1);
    applyXiaozhiPriorityTick(fx.presenter, false, 2);
    expect(!xiaozhiPriorityBlocksPresent(fx.arbiter), "idle again");
    expect(fx.presenter.present(NoticeKind::Success, "Agent done: c", 3), "present after idle");
    expect(fx.presenter.isVisible(), "visible again");
}

}  // namespace

int main()
{
    testBusyPreemptsVisibleNoticeAndMotion();
    testIdleAllowsPresentAgain();
    return 0;
}
