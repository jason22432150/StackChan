#include <cstdlib>
#include <iostream>
#include <stackchan/notifications/runtime_limits.h>

using stackchan::notifications::NotificationController;
using stackchan::notifications::NotificationRuntimeProfile;
using stackchan::notifications::kCoreS3MvpRuntimeProfile;
using stackchan::notifications::sanitizeRuntimeProfile;

namespace {
void expect(bool passed, const char* message)
{
    if (!passed) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}
}  // namespace

int main()
{
    const auto sanitized = sanitizeRuntimeProfile(kCoreS3MvpRuntimeProfile);
    expect(sanitized.has_value(), "MVP profile is within hard ceilings");
    expect(sanitized->controller.capacity == 4, "queue uses full delivery-ID ceiling");
    expect(sanitized->controller.capacity == NotificationController::max_capacity, "capacity equals max_capacity");
    expect(sanitized->controller.heartbeat_timeout_ms == 4000, "heartbeat timeout matches Coordinator 4s");
    expect(sanitized->controller.stability_ms == 5000, "stability matches Coordinator 5s");
    expect(sanitized->max_frame_age_ms == 5000, "frame age bound is set");
    expect(sanitized->max_frame_bytes == 1024, "frame byte ceiling is set");
    expect(sanitized->network_timeout_ms == 10000, "network timeout is set");

    NotificationController controller(sanitized->controller);
    expect(controller.state(0) == NotificationController::State::Suspended, "MVP limits construct a controller");
    expect(controller.beginRecovery(1, "v1", 60'000, 0), "MVP limits allow recovery");
    expect(controller.heartbeat(1, 2500) && controller.state(2500) == NotificationController::State::Recovering,
           "stability window still requires sustained heartbeats");
    expect(controller.heartbeat(1, 5000) && controller.state(5000) == NotificationController::State::Active,
           "MVP stability_ms activates after 5s");
    expect(!controller.heartbeat(1, 9001), "MVP heartbeat_timeout_ms suspends after 4s silence");

    NotificationRuntimeProfile bad = kCoreS3MvpRuntimeProfile;
    bad.controller.capacity = NotificationController::max_capacity + 1;
    expect(!sanitizeRuntimeProfile(bad), "capacity above max_capacity fails closed");
    bad = kCoreS3MvpRuntimeProfile;
    bad.controller.heartbeat_timeout_ms = 0;
    expect(!sanitizeRuntimeProfile(bad), "zero heartbeat fails closed");
    bad = kCoreS3MvpRuntimeProfile;
    bad.max_frame_bytes = 5000;
    expect(!sanitizeRuntimeProfile(bad), "oversized frame ceiling fails closed");
    bad = kCoreS3MvpRuntimeProfile;
    bad.network_timeout_ms = -1;
    expect(!sanitizeRuntimeProfile(bad), "negative network timeout fails closed");
}
