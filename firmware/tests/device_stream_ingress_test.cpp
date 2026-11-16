#include <cstdlib>
#include <iostream>
#include <limits>
#include <stackchan/notifications/device_stream_ingress.h>

using stackchan::notifications::DeviceStreamIngress;
using stackchan::notifications::NotificationController;
using State = NotificationController::State;

namespace {
void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

void testScopeFreshnessAndTimeout()
{
    NotificationController controller({2, 20, 5});
    DeviceStreamIngress ingress(controller, 4);
    expect(!ingress.receiveHeartbeat({1, "dev", "v1", 7, 1000}, 0), "unbound heartbeat rejected");
    expect(ingress.bindVerified({1, "dev", "v1", 7, 1100}, 1000, 0), "bind verified peer");
    expect(!ingress.receiveHeartbeat({1, "other", "v1", 7, 1005}, 5), "wrong device rejected");
    expect(!ingress.receiveHeartbeat({1, "dev", "v2", 7, 1005}, 5), "wrong policy rejected");
    expect(!ingress.receiveHeartbeat({1, "dev", "v1", 8, 1005}, 5), "wrong generation rejected");
    expect(!ingress.receiveHeartbeat({1, "dev", "v1", 7, 1006}, 5), "future frame rejected");
    expect(!ingress.receiveHeartbeat({1, "dev", "v1", 7, 1000}, 5), "stale frame rejected");
    expect(!ingress.receiveHeartbeat({1, "dev", "v1", 7, 999}, 5), "previous connection rejected");
    expect(controller.state(5) == State::Recovering, "invalid frames cannot promote connection");
    const DeviceStreamIngress::Frame heartbeat{1, "dev", "v1", 7, 1005};
    expect(ingress.receiveHeartbeat(heartbeat, 5), "fresh heartbeat promotes connection");
    expect(!ingress.receiveHeartbeat(heartbeat, 6), "heartbeat replay rejected");
    expect(!ingress.receiveHeartbeat({1, "dev", "v1", 7, 1004}, 6), "out-of-order heartbeat rejected");
    expect(ingress.receiveIntent({1, "dev", "v1", 7, 1006}, "notice", 1100, 6), "verified intent accepted");
    expect(!ingress.receiveHeartbeat({1, "dev", "v1", 7, 1025}, 25), "heartbeat at timeout cannot revive");
    expect(!controller.takeNext(1, 25), "timeout clears queued work");
}

void testDeadlineConversionAndReconnect()
{
    NotificationController controller({2, 20, 5});
    DeviceStreamIngress ingress(controller, 5);
    expect(ingress.bindVerified({5, "dev", "v1", 1, 1030}, 1000, 100), "bind establishes clock anchor");
    expect(ingress.receiveHeartbeat({5, "dev", "v1", 1, 1005}, 105), "activate");
    const DeviceStreamIngress::Frame intent{5, "dev", "v1", 1, 1006};
    expect(!ingress.receiveIntent(intent, "already-expired", 1006, 106), "expired UTC deadline rejected");
    expect(ingress.receiveIntent(intent, "notice", 1010, 106), "convert UTC deadline");
    expect(!controller.takeNext(5, 110), "converted expiry enforced at boundary");
    expect(ingress.receiveIntent({5, "dev", "v1", 1, 1010}, "pending", 1100, 110), "queue during lease");
    expect(ingress.receiveHeartbeat({5, "dev", "v1", 1, 1011}, 111), "fresh heartbeat");
    expect(ingress.receiveHeartbeat({5, "dev", "v1", 1, 1025}, 125), "heartbeat does not extend lease");
    expect(!ingress.receiveHeartbeat({5, "dev", "v1", 1, 1030}, 130), "policy expires independently");
    expect(ingress.bindVerified({6, "dev", "v2", 2, 2000}, 1030, 130), "policy replacement gets a new session");
    ingress.disconnect(5);
    expect(!ingress.receiveHeartbeat({5, "dev", "v1", 1, 1035}, 135), "old session heartbeat ignored");
    expect(ingress.receiveHeartbeat({6, "dev", "v2", 2, 1035}, 135), "new session remains live");
    expect(!controller.takeNext(6, 135), "no old pending work");
    ingress.disconnect(6);
    expect(controller.state(136) == State::Suspended, "disconnect revokes active session");
    expect(!ingress.bindVerified({6, "dev", "v2", 2, 2000}, 1036, 136), "closed session cannot rebind");
}

void testMissingClockAndOverflow()
{
    NotificationController controller({2, 20, 5});
    DeviceStreamIngress ingress(controller, 5);
    constexpr auto maximum = std::numeric_limits<DeviceStreamIngress::Tick>::max();
    expect(!ingress.bindVerified({1, "dev", "v1", 9, 100}, 0, 0), "missing trusted UTC fails closed");
    expect(!ingress.bindVerified({2, "dev", "v1", 9, 100}, 10, maximum - 1), "deadline overflow rejected");
    expect(controller.state(0) == State::Suspended, "invalid binding cannot authorize work");
}
}  // namespace

int main()
{
    testScopeFreshnessAndTimeout();
    testDeadlineConversionAndReconnect();
    testMissingClockAndOverflow();
}
