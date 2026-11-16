#include "stream_session_start.h"

#include "runtime_limits.h"

namespace stackchan::notifications {

bool startProvisionedDeviceStream(DeviceStreamTlsClient& client, const StreamProvision& provision)
{
    if (!sanitizeRuntimeProfile(provision.profile) || provision.config.policy_version.empty() ||
        provision.config.policy_expires_utc_ms == 0 ||
        provision.config.max_frame_bytes != provision.profile.max_frame_bytes ||
        provision.config.network_timeout_ms != provision.profile.network_timeout_ms) {
        return false;
    }
    return client.start(provision.config);
}

}  // namespace stackchan::notifications
