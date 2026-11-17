#include "policy_lease.h"

#include <ArduinoJson.h>
#include <algorithm>
#include <cstring>

namespace stackchan::notifications {
namespace {
using Tick = NotificationController::Tick;

class CompactJsonMatch {
public:
    explicit CompactJsonMatch(std::string_view input) : _remaining(input) {}

    std::size_t write(std::uint8_t byte) { return write(&byte, 1); }

    std::size_t write(const std::uint8_t* bytes, std::size_t size)
    {
        if (!_matches ||
            _remaining.substr(0, size) !=
                std::string_view(reinterpret_cast<const char*>(bytes), size)) {
            _matches = false;
            return 0;
        }
        _remaining.remove_prefix(size);
        return size;
    }

    bool complete() const { return _matches && _remaining.empty(); }

private:
    std::string_view _remaining;
    bool _matches = true;
};

std::string_view stringValue(JsonVariantConst value)
{
    const auto text = value.as<JsonString>();
    return text.isNull() ? std::string_view{} : std::string_view(text.c_str(), text.size());
}

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

int digits(std::string_view value)
{
    int result = 0;
    for (char c : value) {
        if (c < '0' || c > '9') {
            return -1;
        }
        result = result * 10 + (c - '0');
    }
    return result;
}

bool leapYear(int year)
{
    return year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
}

// Accepts Coordinator ISO UTC with or without millisecond fraction.
std::optional<Tick> utcMillis(std::string_view value)
{
    const bool with_millis = value.size() == 24;
    if (!(value.size() == 20 || with_millis) || value[4] != '-' || value[7] != '-' || value[10] != 'T' ||
        value[13] != ':' || value[16] != ':' || value.back() != 'Z') {
        return std::nullopt;
    }
    if (with_millis && value[19] != '.') {
        return std::nullopt;
    }
    if (!with_millis && value[19] != 'Z') {
        return std::nullopt;
    }
    const int year = digits(value.substr(0, 4));
    const int month = digits(value.substr(5, 2));
    const int day = digits(value.substr(8, 2));
    const int hour = digits(value.substr(11, 2));
    const int minute = digits(value.substr(14, 2));
    const int second = digits(value.substr(17, 2));
    const int millis = with_millis ? digits(value.substr(20, 3)) : 0;
    if (year < 1970 || month < 1 || month > 12 || day < 1 || hour < 0 || hour > 23 || minute < 0 ||
        minute > 59 || second < 0 || second > 59 || millis < 0) {
        return std::nullopt;
    }
    const int month_days[] = {31, leapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    if (day > month_days[month - 1]) {
        return std::nullopt;
    }
    const auto leapYearsBefore = [](int y) { return (y - 1) / 4 - (y - 1) / 100 + (y - 1) / 400; };
    Tick days = (year - 1970) * 365 + leapYearsBefore(year) - leapYearsBefore(1970) + day - 1;
    for (int i = 0; i < month - 1; ++i) {
        days += month_days[i];
    }
    return ((days * 24 + hour) * 60 * 60 + minute * 60 + second) * 1000 + millis;
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
