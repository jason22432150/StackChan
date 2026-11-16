#pragma once

#include "policy_lease_http_client.h"
#include "stream_provision.h"

#include <optional>

namespace stackchan::notifications {

// GET policy over TLS, then provisionDeviceStream. request.lease is ignored.
// Uses sanitized profile network/frame ceilings for the HTTP fetch.
// Does not open the device-stream WebSocket.
std::optional<StreamProvision> fetchAndProvisionDeviceStream(
    PolicyLeaseHttpClient& http, const StreamProvisionRequest& request);

}  // namespace stackchan::notifications
