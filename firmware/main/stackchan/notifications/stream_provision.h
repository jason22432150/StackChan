#pragma once

#include "device_stream_tls_client.h"
#include "policy_lease.h"
#include "runtime_limits.h"

#include <cstdint>
#include <optional>
#include <string>

namespace stackchan::notifications {

// Inputs for building a DeviceStreamTlsClient::Config before start().
// Policy must already be verified (HTTP fetch + parse, or equivalent).
struct StreamProvisionRequest {
    std::string coordinator_host;
    std::uint16_t port = 0;
    std::string coordinator_ca_pem;
    std::string token;
    std::string device_id;
    std::uint64_t generation = 0;
    PolicyLeaseBinding lease{};
    NotificationRuntimeProfile profile = kCoreS3MvpRuntimeProfile;
    NotificationController::Tick now_utc_ms = 0;
};

struct StreamProvision {
    NotificationRuntimeProfile profile{};
    DeviceStreamTlsClient::Config config{};
};

// Fail-Closed: sanitize profile, bind lease, fill stream Config (does not connect).
std::optional<StreamProvision> provisionDeviceStream(const StreamProvisionRequest& request);

}  // namespace stackchan::notifications
