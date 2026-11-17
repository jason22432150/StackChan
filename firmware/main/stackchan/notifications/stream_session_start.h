#pragma once

#include "device_stream_tls_client.h"
#include "stream_provision.h"

namespace stackchan::notifications {

// Starts an already constructed client with a provisioned Config.
// Caller must construct the client with provision.profile.controller and
// provision.profile.max_frame_age_ms. Does not fetch policy again.
bool startProvisionedDeviceStream(DeviceStreamTlsClient& client, const StreamProvision& provision);

/**
 * P2-04 產品路徑：以已驗證 StreamProvision 武裝 TLS client。
 * Fail-Closed：client 已 started 則拒絕（禁止雙連線）；其餘委派 startProvisionedDeviceStream。
 * 不自動 fetch；呼叫端須先取得 provision（HTTP 或等效）。
 */
bool armProvisionedDeviceStream(DeviceStreamTlsClient& client, const StreamProvision& provision);

/** link_anchor 保留用。 */
bool armProvisionedDeviceStreamLinked();

}  // namespace stackchan::notifications
