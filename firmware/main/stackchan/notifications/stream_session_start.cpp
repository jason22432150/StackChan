#include "stream_session_start.h"

#include "runtime_limits.h"
#include "stream_bootstrap.h"

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

bool armProvisionedDeviceStream(DeviceStreamTlsClient& client, const StreamProvision& provision)
{
    // 已連線則拒絕，避免雙 WebSocket／覆寫 session。
    if (client.started()) {
        return false;
    }
    return startProvisionedDeviceStream(client, provision);
}

bool fetchAndArmDeviceStream(PolicyLeaseHttpClient& http, DeviceStreamTlsClient& client,
                             const StreamProvisionRequest& request)
{
    if (client.started()) {
        return false;
    }
    const auto provision = fetchAndProvisionDeviceStream(http, request);
    if (!provision) {
        return false;
    }
    return armProvisionedDeviceStream(client, *provision);
}

bool armProvisionedDeviceStreamLinked()
{
    return true;
}

}  // namespace stackchan::notifications
