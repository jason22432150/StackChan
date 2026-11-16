#include "stream_provision.h"

namespace stackchan::notifications {

std::optional<StreamProvision> provisionDeviceStream(const StreamProvisionRequest& request)
{
    const auto profile = sanitizeRuntimeProfile(request.profile);
    if (!profile || request.now_utc_ms == 0) {
        return std::nullopt;
    }

    DeviceStreamTlsClient::Config config{};
    config.coordinator_host = request.coordinator_host;
    config.port = request.port;
    config.coordinator_ca_pem = request.coordinator_ca_pem;
    config.token = request.token;
    config.device_id = request.device_id;
    config.generation = request.generation;
    config.max_frame_bytes = profile->max_frame_bytes;
    config.network_timeout_ms = profile->network_timeout_ms;

    if (!applyPolicyLeaseToStreamFields(
            config.policy_version, config.policy_expires_utc_ms, request.lease, request.now_utc_ms)) {
        return std::nullopt;
    }

    StreamProvision provision{};
    provision.profile = *profile;
    provision.config = std::move(config);
    return provision;
}

}  // namespace stackchan::notifications
