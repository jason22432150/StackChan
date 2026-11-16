#pragma once

#include "notification_controller.h"

namespace stackchan::notifications {

// Boundary for decoded frames. The caller owns TLS peer verification, policy
// and revocation checks, and full JSON contract validation.
class DeviceStreamIngress {
public:
    using Tick = NotificationController::Tick;
    using SessionId = NotificationController::SessionId;

    struct VerifiedBinding {
        SessionId session;
        std::string_view device_id;
        std::string_view policy_version;
        std::uint64_t generation;
        Tick policy_expires_utc_ms;
    };

    struct Frame {
        SessionId session;
        std::string_view device_id;
        std::string_view policy_version;
        std::uint64_t generation;
        Tick sent_utc_ms;
    };

    DeviceStreamIngress(NotificationController& controller, Tick max_frame_age_ms);
    DeviceStreamIngress(const DeviceStreamIngress&) = delete;
    DeviceStreamIngress& operator=(const DeviceStreamIngress&) = delete;
    bool bindVerified(VerifiedBinding binding, Tick utc_ms, Tick now);
    void disconnect(SessionId session);
    bool receiveHeartbeat(Frame frame, Tick now);
    bool receiveIntent(Frame frame, std::string_view delivery_id, Tick expires_utc_ms, Tick now);

private:
    bool accepts(Frame frame, Tick now);

    NotificationController& _controller;
    const Tick _max_frame_age;
    SessionId _session = 0;
    std::uint64_t _generation = 0;
    std::array<char, NotificationController::max_id_bytes + 1> _device{};
    std::array<char, NotificationController::max_id_bytes + 1> _policy{};
    Tick _bound_at = 0;
    Tick _bound_utc = 0;
    Tick _last_heartbeat_utc = 0;
    bool _bound = false;
};

}  // namespace stackchan::notifications
