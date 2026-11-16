#include <cstdlib>
#include <iostream>
#include <string>
#include <stackchan/notifications/notification_controller.h>

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

void testRecoveryAndExpiry()
{
    NotificationController controller({2, 10, 12});
    expect(controller.state(0) == State::Suspended, "startup denies notifications");
    expect(controller.beginRecovery(1, "policy", 30, 0), "verified policy starts recovery");
    expect(!controller.enqueue(1, "policy", "a", 20, 0), "recovery denies enqueue");
    expect(controller.heartbeat(1, 8), "heartbeat sustains recovery");
    expect(controller.state(12) == State::Recovering, "elapsed time alone cannot activate");
    expect(controller.heartbeat(1, 12) && controller.state(12) == State::Active, "stable heartbeat activates");
    expect(!controller.enqueue(1, "old-policy", "a", 20, 12), "mismatched policy is rejected");
    expect(controller.enqueue(1, "policy", "a", 40, 12), "valid delivery");
    expect(controller.heartbeat(1, 20), "valid heartbeat");
    expect(controller.heartbeat(1, 29), "heartbeat before policy deadline");
    expect(!controller.takeNext(1, 30), "policy expiry blocks dequeue despite fresh heartbeat");
    expect(controller.state(30) == State::Suspended && !controller.heartbeat(1, 30), "expired session stays suspended");
    expect(!controller.beginRecovery(1, "policy", 80, 31), "old identity cannot reopen");
    expect(controller.beginRecovery(2, "policy", 80, 31), "fresh identity can reconnect");
    expect(controller.heartbeat(2, 38) && controller.heartbeat(2, 43), "reconnect stabilizes again");
    expect(!controller.takeNext(2, 43), "reconnect cannot inherit old deliveries");
}

void testQueueAndSessionIsolation()
{
    NotificationController controller({2, 20, 1});
    expect(controller.beginRecovery(1, "policy", 100, 0) && controller.heartbeat(1, 1), "activation");
    const std::string longest(NotificationController::max_id_bytes, 'x');
    expect(!controller.enqueue(1, "policy", longest + "x", 90, 1), "oversized delivery is rejected");
    expect(!controller.enqueue(1, "policy", std::string_view("a\0b", 3), 90, 1), "embedded null is rejected");
    expect(!controller.enqueue(1, "policy", "old", 1, 1), "TTL boundary");
    expect(controller.enqueue(1, "policy", "short", 3, 1), "first delivery");
    expect(!controller.enqueue(1, "policy", "short", 4, 2), "pending duplicate is rejected");
    expect(controller.enqueue(1, "policy", longest, 90, 2), "maximum supported delivery ID");
    expect(!controller.enqueue(1, "policy", "third", 90, 2), "full queue rejects new deliveries");
    expect(controller.enqueue(1, "policy", "third", 90, 3), "expired pending delivery frees space");
    const auto first = controller.takeNext(1, 3);
    expect(first && std::string_view(first->id.data()) == longest, "remaining FIFO order and terminated ID");
    expect(controller.beginRecovery(2, "new-policy", 100, 3), "replacement resets queue");
    controller.suspend(1);
    expect(!controller.heartbeat(1, 50), "stale heartbeat cannot affect new session clock");
    expect(controller.heartbeat(2, 4) && !controller.takeNext(2, 4), "stale disconnect cannot cancel replacement");
    expect(controller.enqueue(2, "new-policy", "new", 90, 4), "valid replacement delivery");
    controller.suspend(2);
    expect(!controller.takeNext(2, 5), "revocation invalidates pending delivery");
}

void testFailClosedConfigurationAndClock()
{
    NotificationController oversized({NotificationController::max_capacity + 1, 20, 1});
    expect(!oversized.beginRecovery(1, "policy", 40, 0), "invalid capacity denies recovery");
    NotificationController zero_lease({1, 0, 1});
    expect(!zero_lease.beginRecovery(1, "policy", 40, 0), "zero heartbeat limit denies recovery");

    NotificationController controller({1, 10, 1});
    expect(!controller.beginRecovery(1, "", 40, 0), "empty policy version is invalid");
    expect(controller.beginRecovery(2, "policy", 40, 1), "verified policy");
    expect(controller.heartbeat(2, 2), "stable heartbeat");
    expect(!controller.heartbeat(2, 12), "heartbeat at the exact deadline cannot resume session");
    expect(controller.beginRecovery(3, "policy", 40, 12) && controller.heartbeat(3, 13), "fresh session");
    expect(controller.state(12) == State::Suspended, "monotonic clock regression fails closed");
    expect(!controller.beginRecovery(4, "policy", 40, 12), "reconnect may not reset monotonic clock");
}
}  // namespace

int main()
{
    static_assert(sizeof(NotificationController) <= 1024);
    testRecoveryAndExpiry();
    testQueueAndSessionIsolation();
    testFailClosedConfigurationAndClock();
}
