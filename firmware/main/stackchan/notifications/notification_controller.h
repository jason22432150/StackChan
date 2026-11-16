#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>

namespace stackchan::notifications {

// All calls belong to one execution context. Transport authenticates the peer,
// validates the envelope and policy, and converts deadlines to monotonic ms.
class NotificationController {
public:
    using Tick = std::uint64_t;
    using SessionId = std::uint64_t;
    static constexpr std::size_t max_capacity = 4;
    static constexpr std::size_t max_id_bytes = 128;

    enum class State { Suspended, Recovering, Active };

    struct Limits {
        std::size_t capacity;
        Tick heartbeat_timeout_ms;
        Tick stability_ms;
    };

    struct PendingDelivery {
        std::array<char, max_id_bytes + 1> id{};
        Tick expires_at{};
    };

    explicit NotificationController(Limits limits);

    // A fresh local session ID is required on reconnect or policy replacement.
    bool beginRecovery(SessionId session, std::string_view policy_version, Tick policy_until, Tick now);
    bool heartbeat(SessionId session, Tick now);
    void suspend(SessionId session);
    State state(Tick now);
    bool enqueue(SessionId session, std::string_view policy_version, std::string_view id, Tick expires_at, Tick now);
    std::optional<PendingDelivery> takeNext(SessionId session, Tick now);

private:
    void discardExpired(Tick now);

    Limits _limits;
    State _state = State::Suspended;
    SessionId _session = 0;
    std::array<char, max_id_bytes + 1> _policy_version{};
    Tick _policy_until = 0;
    Tick _connected_at = 0;
    Tick _last_heartbeat = 0;
    Tick _last_tick = 0;
    std::array<PendingDelivery, max_capacity> _queue{};
    std::size_t _size = 0;
};

}  // namespace stackchan::notifications
