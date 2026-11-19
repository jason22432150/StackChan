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
}  // namespace

int main()
{
    testBindPulseAndEnqueue();
    testExpiryConversion();
}
