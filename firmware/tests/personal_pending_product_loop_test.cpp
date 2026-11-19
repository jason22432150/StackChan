#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

#include <stackchan/notifications/fail_closed_guard.h>
#include <stackchan/notifications/notification_controller.h>
#include <stackchan/notifications/notification_presenter.h>
#include <stackchan/notifications/notification_product_loop.h>
#include <stackchan/notifications/personal_pending_ingress.h>
#include <stackchan/notifications/personal_pending_json.h>
#include <stackchan/notifications/presentation_receipt.h>
#include <stackchan/notifications/resource_arbiter.h>

using stackchan::notifications::FailClosedGuard;
using stackchan::notifications::LvglLockHooks;
using stackchan::notifications::LvglLockedUiPort;
using stackchan::notifications::NoticeKind;
using stackchan::notifications::NotificationController;
using stackchan::notifications::NotificationPresenter;
using stackchan::notifications::NotificationProductLoop;
using stackchan::notifications::NotificationUiPort;
using stackchan::notifications::PersonalPendingIngress;
using stackchan::notifications::PresentationReceiptTracker;
using stackchan::notifications::ResourceArbiter;
using stackchan::notifications::applyPersonalPendingJson;
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

// expires_at = 2000ms UTC；bound_utc=1000 → 可在 now≈2 呈現
constexpr char kPendingBody[] =
    R"({"items":[{"schema_version":"0.1","notification_id":"ntf_evt_1","delivery_id":"dlv_evt_1",)"
    R"("device_id":"cores3_primary","event_ids":["evt_1"],"priority":50,"policy_version":"pol_v1",)"
    R"("generation":1,"expires_at":"1970-01-01T00:00:02.000Z",)"
    R"("presentation_policy":{"ui":true,"audio":false,"motion":true,"tts":false},)"
    R"("presentation_profile":"personal.basic_notice","created_at":"1970-01-01T00:00:01.000Z"}],"count":1})";

struct Fixture {
    NotificationController controller{{2, 20, 1}};
    PersonalPendingIngress ingress{controller, 50};
    ResourceArbiter arbiter;
    FakeUi inner;
    LvglLockedUiPort ui{inner, LvglLockHooks{lockFn, unlockFn, nullptr}};
    NotificationPresenter presenter{arbiter, ui};
    PresentationReceiptTracker receipts;
    FailClosedGuard guard{controller, presenter, &receipts};
    NotificationProductLoop loop{controller, guard, presenter, &receipts};
};

void testPendingJsonFeedsProductLoop()
{
    Fixture fx;
    expect(fx.ingress.bind({1, "cores3_primary", "pol_v1", 1, 60'000}, 1000, 0), "bind personal");
    expect(fx.ingress.pulse(1001, 1), "activate");
    expect(fx.controller.state(1) == State::Active, "active");
    expect(applyPersonalPendingJson(fx.ingress, kPendingBody, 2048, 2) == 1, "apply one item");
    fx.loop.attachSession(1);
    expect(fx.loop.tick(2, 1002) == Outcome::Presented, "present via product loop");
    expect(!fx.inner.ops.empty() && fx.inner.ops.back() == "show:Agent update: dlv_evt_1",
           "basic notice");
}

void testPollPersonalPendingSequence()
{
    Fixture fx;
    expect(fx.loop.tick(1, 1001) == Outcome::Idle, "unbound stays idle");
    expect(fx.ingress.bind({1, "cores3_primary", "pol_v1", 1, 60'000}, 1000, 0), "bind");
    // 與 notificationProductLoopPollPersonalPending 相同步驟（host 不連 poll.cpp／esp_timer）
    expect(fx.ingress.pulse(1001, 1), "pulse");
    expect(applyPersonalPendingJson(fx.ingress, kPendingBody, 2048, 1) == 1, "apply");
    fx.loop.attachSession(1);
    expect(fx.loop.tick(1, 1001) == Outcome::Presented, "present after personal poll sequence");
    expect(!fx.inner.ops.empty() && fx.inner.ops.back() == "show:Agent update: dlv_evt_1", "ui show");
}
}  // namespace

int main()
{
    testPendingJsonFeedsProductLoop();
    testPollPersonalPendingSequence();
}
