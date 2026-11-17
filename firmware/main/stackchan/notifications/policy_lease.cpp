#include "policy_lease.h"

#include "notification_payload.h"

#include <ArduinoJson.h>
#include <algorithm>
#include <cstring>

namespace stackchan::notifications {
namespace {
using Tick = NotificationController::Tick;
using payload::CompactJsonMatch;
using payload::stringValue;
using payload::utcMillis;

template <std::size_t N>
std::string_view leaseField(const std::array<char, N>& field)
{
    const auto terminator = std::find(field.begin(), field.end(), '\0');
    if (terminator == field.end()) {
        return {};
    }
    return {field.data(), static_cast<std::size_t>(terminator - field.begin())};
}

bool identifier(std::string_view value)
{
    return !value.empty() && value.size() <= NotificationController::max_id_bytes &&
           std::all_of(value.begin(), value.end(), [](unsigned char c) {
               return c >= 0x21 && c <= 0x7e;
           });
}

bool privacyMode(std::string_view value)
{
    return value == "private" || value == "public" || value == "strict";
}

bool copyField(std::array<char, NotificationController::max_id_bytes + 1>& dest, std::string_view value)
{
    if (!identifier(value)) {
        return false;
    }
    std::memcpy(dest.data(), value.data(), value.size());
    dest[value.size()] = '\0';
    return true;
}

bool copyShort(std::array<char, 16>& dest, std::string_view value)
{
    if (value.size() >= dest.size()) {
        return false;
    }
    std::memcpy(dest.data(), value.data(), value.size());
    dest[value.size()] = '\0';
    return true;
}
}  // namespace

std::optional<PolicyLeaseBinding> parsePolicyLeaseJson(
    std::string_view json, std::size_t max_bytes, Tick now_utc_ms)
{
    if (json.empty() || json.size() > max_bytes || now_utc_ms == 0) {
        return std::nullopt;
    }
    JsonDocument document;
    if (deserializeJson(document, json.data(), json.size(), DeserializationOption::NestingLimit(2))) {
        return std::nullopt;
    }
    CompactJsonMatch match(json);
    serializeJson(document, match);
    if (!match.complete()) {
        return std::nullopt;
    }
    const auto object = document.as<JsonObjectConst>();
    const bool has_revoked = !object["revoked"].isUnbound();
    if (object.size() != (has_revoked ? 5u : 4u) || !object["policy_id"].is<const char*>() ||
        !object["version"].is<const char*>() || !object["privacy_mode"].is<const char*>() ||
        !object["valid_until"].is<const char*>() || (has_revoked && !object["revoked"].is<bool>()) ||
        (has_revoked && object["revoked"].as<bool>())) {
        return std::nullopt;
    }
    const auto policy_id = stringValue(object["policy_id"]);
    const auto version = stringValue(object["version"]);
    const auto mode = stringValue(object["privacy_mode"]);
    const auto expires = utcMillis(stringValue(object["valid_until"]));
    if (!expires || *expires <= now_utc_ms || !privacyMode(mode)) {
        return std::nullopt;
    }
    PolicyLeaseBinding binding{};
    if (!copyField(binding.policy_id, policy_id) || !copyField(binding.version, version) ||
        !copyShort(binding.privacy_mode, mode)) {
        return std::nullopt;
    }
    binding.expires_utc_ms = *expires;
    return binding;
}

bool bindPolicyLease(PolicyLeaseBinding& out, const PolicyLeaseBinding& lease, Tick now_utc_ms)
{
    if (now_utc_ms == 0 || lease.expires_utc_ms <= now_utc_ms ||
        !identifier(leaseField(lease.policy_id)) || !identifier(leaseField(lease.version)) ||
        !privacyMode(leaseField(lease.privacy_mode))) {
        return false;
    }
    out = lease;
    return true;
}

bool applyPolicyLeaseToStreamFields(
    std::string& policy_version,
    Tick& policy_expires_utc_ms,
    const PolicyLeaseBinding& lease,
    Tick now_utc_ms)
{
    PolicyLeaseBinding bound{};
    if (!bindPolicyLease(bound, lease, now_utc_ms)) {
        return false;
    }
    policy_version.assign(bound.version.data());
    policy_expires_utc_ms = bound.expires_utc_ms;
    return true;
}

}  // namespace stackchan::notifications
