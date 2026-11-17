#pragma once

#include "device_stream_ingress.h"
#include "stream_provision.h"

#include <optional>
#include <string_view>

namespace stackchan::notifications {

/**
 * 裝置對 Coordinator loopback 的軟路徑握手輸入。
 * 呼叫端須已完成 TLS 對等端／CA 驗證；本函式不開 socket。
 * `provision.lease` 會被 policy_json 解析結果覆寫。
 */
struct DeviceLoopbackHandshakeRequest {
    std::string_view policy_json{};
    std::size_t max_policy_bytes = 0;
    StreamProvisionRequest provision{};
    DeviceStreamIngress::SessionId session = 0;
    DeviceStreamIngress::Tick trusted_peer_utc_ms = 0;
    DeviceStreamIngress::Tick now_ms = 0;
};

struct DeviceLoopbackHandshakeResult {
    StreamProvision provision{};
    PolicyLeaseBinding lease{};
};

/**
 * 解析 loopback GET /policy JSON → provisionDeviceStream → DeviceStreamIngress::bindVerified。
 * 任一階段失敗即 Fail-Closed（nullopt）；重試須使用遞增的 session（與 bindVerified 語意相同）。
 */
std::optional<DeviceLoopbackHandshakeResult> completeDeviceLoopbackHandshake(
    DeviceStreamIngress& ingress, DeviceLoopbackHandshakeRequest request);

/** link_anchor／測試：確認握手進入點已連結（不執行網路）。 */
bool deviceLoopbackHandshakeLinked();

}  // namespace stackchan::notifications
