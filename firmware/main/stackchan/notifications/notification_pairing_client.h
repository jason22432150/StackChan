#pragma once

#include "notification_product_runtime.h"

#include <optional>

namespace stackchan::notifications {

// Explicit local pairing calls, serialized by the caller outside the LVGL lock.
class NotificationPairingClient {
public:
    enum class Completion { Pending, Delivered, Unavailable };

    NotificationPairingClient() = default;
    NotificationPairingClient(const NotificationPairingClient&) = delete;
    NotificationPairingClient& operator=(const NotificationPairingClient&) = delete;

    // Returns only the human confirmation code. The claim remains private.
    // The pairing and stream listeners share a trusted host and CA.
    std::optional<std::string> start(NotificationPairingEndpoint pairing_endpoint, std::uint16_t stream_port);
    Completion complete();
    void cancel();

private:
    NotificationPairingEndpoint _endpoint;
    std::string _pairing_id;
    std::string _claim;
    std::uint64_t _expires_at = 0;
};

}  // namespace stackchan::notifications
