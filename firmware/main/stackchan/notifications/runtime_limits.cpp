#include "runtime_limits.h"

namespace stackchan::notifications {
namespace {
constexpr NotificationController::Tick kMaxHeartbeatTimeoutMs = 60'000;
constexpr NotificationController::Tick kMaxStabilityMs = 60'000;
constexpr NotificationController::Tick kMaxFrameAgeMs = 60'000;
constexpr std::size_t kMaxFrameBytesCeiling = 4096;
constexpr int kMaxNetworkTimeoutMs = 60'000;
}  // namespace

std::optional<NotificationRuntimeProfile> sanitizeRuntimeProfile(const NotificationRuntimeProfile& profile)
{
    if (profile.controller.capacity == 0 ||
        profile.controller.capacity > NotificationController::max_capacity ||
        profile.controller.heartbeat_timeout_ms == 0 ||
        profile.controller.heartbeat_timeout_ms > kMaxHeartbeatTimeoutMs ||
        profile.controller.stability_ms == 0 ||
        profile.controller.stability_ms > kMaxStabilityMs ||
        profile.max_frame_age_ms == 0 || profile.max_frame_age_ms > kMaxFrameAgeMs ||
        profile.max_frame_bytes == 0 || profile.max_frame_bytes > kMaxFrameBytesCeiling ||
        profile.network_timeout_ms <= 0 || profile.network_timeout_ms > kMaxNetworkTimeoutMs) {
        return std::nullopt;
    }
    return profile;
}

}  // namespace stackchan::notifications
