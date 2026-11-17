#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>
#include <stackchan/notifications/notification_presenter.h>
#include <stackchan/notifications/resource_arbiter.h>

using stackchan::notifications::LvglLockHooks;
using stackchan::notifications::LvglLockedUiPort;
using stackchan::notifications::NoticeKind;
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

struct FakeUi final : NotificationUiPort {
    struct Event {
        enum class Type { Show, Clear } type;
        NoticeKind kind = NoticeKind::Neutral;
        std::string text;
    };
    std::vector<Event> events;
    bool fail_show = false;

    bool show(NoticeKind kind, std::string_view text) override
    {
        if (fail_show) {
            return false;
        }
        events.push_back({Event::Type::Show, kind, std::string(text)});
        return true;
    }

    void clear() override { events.push_back({Event::Type::Clear}); }
};

struct LockCounter {
    int locks = 0;
    int unlocks = 0;
    bool refuse = false;
};

void lockFn(void* ctx)
{
    auto* counter = static_cast<LockCounter*>(ctx);
    ++counter->locks;
}

void unlockFn(void* ctx)
{
    auto* counter = static_cast<LockCounter*>(ctx);
    ++counter->unlocks;
}

void testPresentNeutralAndSuccessUnderLock()
{
    ResourceArbiter arbiter;
    FakeUi inner;
    LockCounter locks;
    LvglLockedUiPort ui(inner, LvglLockHooks{lockFn, unlockFn, &locks});
    NotificationPresenter presenter(arbiter, ui);

    expect(presenter.present(NoticeKind::Neutral, "agent done", 10), "present neutral");
    expect(presenter.isVisible(), "visible");
    expect(presenter.kind() == NoticeKind::Neutral, "neutral kind");
    expect(locks.locks == 1 && locks.unlocks == 1, "one lock pair for show");
    expect(inner.events.size() == 1 && inner.events[0].type == FakeUi::Event::Type::Show, "show recorded");
    expect(inner.events[0].text == "agent done", "text");

    expect(presenter.present(NoticeKind::Success, "verified ok", 20), "present success");
    expect(presenter.kind() == NoticeKind::Success, "success kind");
    expect(locks.locks == 3 && locks.unlocks == 3, "clear old + show new under lock");
}

void testStaleGenerationCannotKeepShowingAfterInterrupt()
{
    ResourceArbiter arbiter;
    FakeUi inner;
    LockCounter locks;
    LvglLockedUiPort ui(inner, LvglLockHooks{lockFn, unlockFn, &locks});
    NotificationPresenter presenter(arbiter, ui);

    expect(presenter.present(NoticeKind::Neutral, "hello", 1), "present");
    const auto gen = presenter.generation();
    const auto confirmation = presenter.interrupt(2);
    expect(confirmation.generation_bumped, "generation bumped");
    expect(!presenter.isVisible(), "cleared");
    expect(!arbiter.mayCommit(gen, ResourceArbiter::Resource::Ui, 3), "stale mayCommit false");
    expect(inner.events.back().type == FakeUi::Event::Type::Clear, "clear after interrupt");
}

void testXiaozhiBusyRejectsPresentAndClearsVisible()
{
    ResourceArbiter arbiter;
    FakeUi inner;
    LockCounter locks;
    LvglLockedUiPort ui(inner, LvglLockHooks{lockFn, unlockFn, &locks});
    NotificationPresenter presenter(arbiter, ui);

    expect(presenter.present(NoticeKind::Success, "ok", 1), "present");
    presenter.onXiaozhiActivity(XiaozhiActivity::Busy, 2);
    expect(!presenter.isVisible(), "busy clears");
    expect(!presenter.present(NoticeKind::Neutral, "again", 3), "busy rejects present");

    presenter.onXiaozhiActivity(XiaozhiActivity::Idle, 4);
    expect(presenter.present(NoticeKind::Neutral, "after", 5), "idle allows present");
}

void testDismissReleasesWithoutBumpingGeneration()
{
    ResourceArbiter arbiter;
    FakeUi inner;
    LockCounter locks;
    LvglLockedUiPort ui(inner, LvglLockHooks{lockFn, unlockFn, &locks});
    NotificationPresenter presenter(arbiter, ui);

    expect(presenter.present(NoticeKind::Neutral, "temp", 1), "present");
    const auto gen = presenter.generation();
    presenter.dismiss(2);
    expect(!presenter.isVisible(), "dismissed");
    expect(arbiter.currentGeneration() == gen, "dismiss does not bump generation");
    expect(!arbiter.hasLease(ResourceArbiter::Resource::Ui), "ui lease released");
}

void testRejectsUnsafeOrOversizedTextAndMissingLock()
{
    ResourceArbiter arbiter;
    FakeUi inner;
    LvglLockedUiPort bad(inner, LvglLockHooks{});
    NotificationPresenter broken(arbiter, bad);
    expect(!broken.present(NoticeKind::Neutral, "x", 1), "missing lock hooks fail closed");

    LockCounter locks;
    LvglLockedUiPort ui(inner, LvglLockHooks{lockFn, unlockFn, &locks});
    NotificationPresenter presenter(arbiter, ui);
    expect(!presenter.present(NoticeKind::Neutral, "", 2), "empty text");
    expect(!presenter.present(NoticeKind::Neutral, std::string(129, 'a'), 3), "oversized");
    expect(!presenter.present(NoticeKind::Neutral, "bad\"x", 4), "unsafe quote");
}

void testShowFailureReleasesLease()
{
    ResourceArbiter arbiter;
    FakeUi inner;
    inner.fail_show = true;
    LockCounter locks;
    LvglLockedUiPort ui(inner, LvglLockHooks{lockFn, unlockFn, &locks});
    NotificationPresenter presenter(arbiter, ui);
    expect(!presenter.present(NoticeKind::Success, "nope", 1), "show failure");
    expect(!presenter.isVisible(), "not visible");
    expect(!arbiter.hasLease(ResourceArbiter::Resource::Ui), "lease released on show failure");
}
}  // namespace

int main()
{
    testPresentNeutralAndSuccessUnderLock();
    testStaleGenerationCannotKeepShowingAfterInterrupt();
    testXiaozhiBusyRejectsPresentAndClearsVisible();
    testDismissReleasesWithoutBumpingGeneration();
    testRejectsUnsafeOrOversizedTextAndMissingLock();
    testShowFailureReleasesLease();
    return 0;
}
