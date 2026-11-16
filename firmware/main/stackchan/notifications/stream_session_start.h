#pragma once

#include "device_stream_tls_client.h"
#include "stream_provision.h"

namespace stackchan::notifications {

// Starts an already constructed client with a provisioned Config.
// Caller must construct the client with provision.profile.controller and
// provision.profile.max_frame_age_ms. Does not fetch policy again.
bool startProvisionedDeviceStream(DeviceStreamTlsClient& client, const StreamProvision& provision);

}  // namespace stackchan::notifications
