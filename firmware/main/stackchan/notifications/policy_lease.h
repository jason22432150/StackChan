#pragma once

#include "notification_controller.h"

#include <array>
#include <cstddef>
#include <optional>
#include <string>
#include <string_view>

namespace stackchan::notifications {

// Verified OpenAPI Policy snapshot for binding DeviceStreamTlsClient before connect.
struct PolicyLeaseBinding {
    std::array<char, NotificationController::max_id_bytes + 1> policy_id{};
    std::array<char, NotificationController::max_id_bytes + 1> version{};
    std::array<char, 16> privacy_mode{};
    NotificationController::Tick expires_utc_ms = 0;
};

// Parses GET /v1/devices/{id}/policy JSON. Fail-Closed on revoked, expired,
// unknown privacy mode, trailing data, or fields outside the OpenAPI Policy shape.
std::optional<PolicyLeaseBinding> parsePolicyLeaseJson(
    std::string_view json, std::size_t max_bytes, NotificationController::Tick now_utc_ms);

// Copies a verified lease into stream config fields. Refuses expired leases.
bool bindPolicyLease(
    PolicyLeaseBinding& out, const PolicyLeaseBinding& lease, NotificationController::Tick now_utc_ms);

// Copies a verified lease into DeviceStreamTlsClient policy fields.
bool applyPolicyLeaseToStreamFields(
    std::string& policy_version,
    NotificationController::Tick& policy_expires_utc_ms,
    const PolicyLeaseBinding& lease,
    NotificationController::Tick now_utc_ms);

}  // namespace stackchan::notifications
