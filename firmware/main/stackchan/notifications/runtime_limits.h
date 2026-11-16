#pragma once

#include "notification_controller.h"

#include <cstddef>
#include <cstdint>
#include <optional>

namespace stackchan::notifications {

// P0-04 CoreS3 baseline (2026-11-16): max update gap 184,054 us, max LVGL hold
// 117,429 us, internal heap low-water 5,424 bytes. R-006 worst-case revoke time
// is not measured yet; these MVP defaults are testable and may shrink on device
// Gate, but must stay within the hard ceilings enforced by sanitizeRuntimeProfile.
struct NotificationRuntimeProfile {
    NotificationController::Limits controller;
    NotificationController::Tick max_frame_age_ms;
    std::size_t max_frame_bytes;
    int network_timeout_ms;
};

// capacity=4 (== max_capacity; delivery IDs only)
// heartbeat_timeout_ms=4000: ~21x worst UI gap; aligned with Coordinator 4s
// stability_ms=5000: reconnect stability; aligned with Coordinator 5s
// max_frame_age_ms=5000: reject stale heartbeat/intent frames
// max_frame_bytes=1024: single WebSocket text frame ceiling
// network_timeout_ms=10000: TLS connect/read ceiling
inline constexpr NotificationRuntimeProfile kCoreS3MvpRuntimeProfile{
    {4, 4000, 5000},
    5000,
    1024,
    10000,
};

// Fail-Closed: profiles outside hard ceilings must not construct controllers.
std::optional<NotificationRuntimeProfile> sanitizeRuntimeProfile(const NotificationRuntimeProfile& profile);

}  // namespace stackchan::notifications
