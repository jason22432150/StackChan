#include <cstdlib>
#include <iostream>
#include <string_view>
#include <stackchan/notifications/personal_pending_ingress.h>

using stackchan::notifications::NotificationController;
using stackchan::notifications::PersonalPendingIngress;
using State = NotificationController::State;

namespace {
void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

void testBindPulseAndEnqueue()
{
    NotificationController controller({2, 20, 1});
    PersonalPendingIngress ingress(controller, 5);
    expect(!ingress.pulse(1001, 1), "unbound pulse rejected");
    expect(ingress.bind({1, "cores3_primary", "pol_v1", 3, 10'000}, 1000, 0), "bind");
    expect(ingress.pulse(1001, 1), "first pulse");
    expect(controller.state(1) == State::Active, "active after stability");
    expect(!ingress.pulse(1001, 2), "replay pulse rejected");
    expect(!ingress.pulse(1000, 2), "non-increasing pulse rejected");
    expect(ingress.pulse(1002, 2), "fresh pulse");
    expect(ingress.receiveItem("cores3_primary", "pol_v1", 3, "dlv_evt_1", 2000, 3), "enqueue");
    expect(!ingress.receiveItem("other", "pol_v1", 3, "dlv_x", 2000, 4), "wrong device");
    const auto next = controller.takeNext(1, 4);
    expect(next && std::string_view{next->id.data()} == "dlv_evt_1", "take delivery");
}

void testExpiryConversion()
{
    NotificationController controller({2, 20, 1});
    PersonalPendingIngress ingress(controller, 5);
    expect(ingress.bind({2, "dev", "v1", 1, 5000}, 1000, 0), "bind");
    expect(ingress.pulse(1001, 1), "pulse");
    expect(!ingress.receiveItem("dev", "v1", 1, "late", 1001, 2), "already expired");
    expect(ingress.receiveItem("dev", "v1", 1, "ok", 1010, 2), "deadline converted");
    expect(!controller.takeNext(2, 12), "expired at mono boundary");
}

void testPulseAllowsUtcSlightlyAheadOfEstimate()
{
    NotificationController controller({2, 20, 1});
    PersonalPendingIngress ingress(controller, 5);
    // bind＠utc=1000, mono=0；同 mono 下 wall clock 超前 3ms（仍 < max_skew=5）
    expect(ingress.bind({3, "dev", "v1", 1, 10'000}, 1000, 0), "bind");
    expect(ingress.pulse(1003, 0), "ahead within skew accepted");
    expect(!ingress.pulse(1007, 0), "ahead beyond skew rejected");
}

void testRebindAfterDisconnectNeedsNewerSession()
{
    NotificationController controller({2, 20, 1});
    PersonalPendingIngress ingress(controller, 5);
    expect(ingress.bind({4, "dev", "v1", 1, 10'000}, 1000, 0), "first bind");
    expect(ingress.bound(), "bound");
    expect(!ingress.bind({4, "dev", "v1", 1, 10'000}, 1000, 1), "same session while bound rejected");
    ingress.disconnect(4);
    expect(!ingress.bound(), "unbound after disconnect");
    // Controller beginRecovery 亦要求 session 遞增；pause 後須用更新的 runtime session。
    expect(!ingress.bind({4, "dev", "v1", 1, 10'000}, 1001, 2), "same session after pause rejected");
    expect(ingress.bind({5, "dev", "v1", 1, 10'000}, 1001, 2), "newer session after pause");
    expect(ingress.bound(), "re-bound");
}
}  // namespace

int main()
{
    testBindPulseAndEnqueue();
    testExpiryConversion();
    testPulseAllowsUtcSlightlyAheadOfEstimate();
    testRebindAfterDisconnectNeedsNewerSession();
}
