#include "device_loopback_handshake.h"

namespace stackchan::notifications {

std::optional<DeviceLoopbackHandshakeResult> completeDeviceLoopbackHandshake(
    DeviceStreamIngress& ingress, DeviceLoopbackHandshakeRequest request)
{
    if (request.policy_json.empty() || request.max_policy_bytes == 0 || request.session == 0 ||
        request.trusted_peer_utc_ms == 0) {
        return std::nullopt;
    }

    const auto lease =
        parsePolicyLeaseJson(request.policy_json, request.max_policy_bytes, request.provision.now_utc_ms);
    if (!lease) {
        return std::nullopt;
    }

    request.provision.lease = *lease;
    auto provision = provisionDeviceStream(request.provision);
    if (!provision) {
        return std::nullopt;
    }

    const DeviceStreamIngress::VerifiedBinding binding{
        request.session,
        provision->config.device_id,
        provision->config.policy_version,
        provision->config.generation,
        provision->config.policy_expires_utc_ms,
    };
    if (!ingress.bindVerified(binding, request.trusted_peer_utc_ms, request.now_ms)) {
        return std::nullopt;
    }

    DeviceLoopbackHandshakeResult result{};
    result.provision = std::move(*provision);
    result.lease = *lease;
    return result;
}

bool deviceLoopbackHandshakeLinked()
{
    return true;
}

}  // namespace stackchan::notifications
