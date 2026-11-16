#pragma once

#include "policy_lease.h"

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace stackchan::notifications {

// Fetches GET /v1/devices/{deviceId}/policy over TLS with an explicit Coordinator CA.
// Caller supplies a synchronized UTC clock. Redirects and non-200 responses fail closed.
class PolicyLeaseHttpClient {
public:
    struct Config {
        std::string coordinator_host;
        std::uint16_t port = 0;
        std::string coordinator_ca_pem;
        std::string token;
        std::string device_id;
        std::size_t max_response_bytes = 0;
        int network_timeout_ms = 0;
    };

    std::optional<PolicyLeaseBinding> fetch(const Config& config, NotificationController::Tick now_utc_ms);
};

}  // namespace stackchan::notifications
