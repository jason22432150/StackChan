#pragma once

#include <stackchan/notifications/notification_product_task.h>
#include <charconv>
#include <optional>
#include <string>
#include <utility>

namespace setup_workers {

// Owns only the pairing request accepted from this page.
class NotificationPairingSession {
public:
    ~NotificationPairingSession() { leave(); }
    NotificationPairingSession() = default;
    NotificationPairingSession(const NotificationPairingSession&) = delete;
    NotificationPairingSession& operator=(const NotificationPairingSession&) = delete;

    bool start(stackchan::notifications::NotificationPairingEndpoint endpoint, std::uint16_t stream_port,
               std::string_view generation)
    {
        if (_owns_request) {
            return false;
        }
        std::uint64_t value = 0;
        if (generation.empty() || generation.size() > 20) {
            return false;
        }
        const auto* end = generation.data() + generation.size();
        const auto parsed = std::from_chars(generation.data(), end, value);
        if (parsed.ec != std::errc{} || parsed.ptr != end) {
            return false;
        }
        // Kconfig's string field can contain literal backslash-n sequences.
        for (std::size_t position = 0; (position = endpoint.coordinator_ca_pem.find("\\n", position)) != std::string::npos;) {
            endpoint.coordinator_ca_pem.replace(position, 2, "\n");
            ++position;
        }
        _owns_request = stackchan::notifications::requestNotificationProductPairing(std::move(endpoint), stream_port, value);
        return _owns_request;
    }

    std::optional<stackchan::notifications::NotificationPairingStatus> poll()
    {
        using namespace stackchan::notifications;
        if (!_owns_request) {
            return std::nullopt;
        }
        const auto snapshot = notificationProductPairingStatus();
        if (snapshot.state == NotificationPairingState::Idle || snapshot.state == NotificationPairingState::Failed ||
            snapshot.state == NotificationPairingState::Cancelled) {
            _owns_request = false;
        }
        return snapshot;
    }

    void leave()
    {
        using namespace stackchan::notifications;
        if (_owns_request) {
            const auto state = notificationProductPairingStatus().state;
            if (state == NotificationPairingState::Starting || state == NotificationPairingState::AwaitingApproval) {
                cancelNotificationProductPairing();
            }
            _owns_request = false;
        }
    }

private:
    bool _owns_request = false;
};

}  // namespace setup_workers
