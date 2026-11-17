#pragma once

#include "device_stream_tls_client.h"
#include "policy_lease_http_client.h"
#include "stream_provision.h"

#include <optional>

namespace stackchan::notifications {

// GET policy over TLS, then provisionDeviceStream. request.lease is ignored.
// Uses sanitized profile network/frame ceilings for the HTTP fetch.
// Does not open the device-stream WebSocket.
std::optional<StreamProvision> fetchAndProvisionDeviceStream(
    PolicyLeaseHttpClient& http, const StreamProvisionRequest& request);

/**
 * P2-04 憑證軟路徑：GET policy → provision → armProvisionedDeviceStream。
 * Fail-Closed：client 已 started、HTTP／租約失敗、或 upgrade 失敗皆回 false 且不留下半開連線意圖。
 * 成功後 client.started()==true；呼叫端仍須由產品主迴圈 poll。
 */
bool fetchAndArmDeviceStream(PolicyLeaseHttpClient& http, DeviceStreamTlsClient& client,
                             const StreamProvisionRequest& request);

}  // namespace stackchan::notifications
