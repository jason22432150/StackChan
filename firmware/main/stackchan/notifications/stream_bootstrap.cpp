#include "stream_bootstrap.h"

namespace stackchan::notifications {

std::optional<StreamProvision> fetchAndProvisionDeviceStream(
    PolicyLeaseHttpClient& http, const StreamProvisionRequest& request)
{
    const auto profile = sanitizeRuntimeProfile(request.profile);
    if (!profile || request.now_utc_ms == 0) {
        return std::nullopt;
    }

    PolicyLeaseHttpClient::Config http_config{};
    http_config.coordinator_host = request.coordinator_host;
    http_config.port = request.port;
    http_config.coordinator_ca_pem = request.coordinator_ca_pem;
    http_config.token = request.token;
    http_config.device_id = request.device_id;
    http_config.max_response_bytes = profile->max_frame_bytes;
    http_config.network_timeout_ms = profile->network_timeout_ms;

    const auto lease = http.fetch(http_config, request.now_utc_ms);
    if (!lease) {
        return std::nullopt;
    }

    StreamProvisionRequest provisioned = request;
    provisioned.lease = *lease;
    provisioned.profile = *profile;
    return provisionDeviceStream(provisioned);
}

}  // namespace stackchan::notifications
