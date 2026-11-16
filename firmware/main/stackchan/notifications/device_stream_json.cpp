#include "device_stream_json.h"

#include <ArduinoJson.h>
#include <algorithm>
#include <optional>

namespace stackchan::notifications {
namespace {
using Tick = DeviceStreamIngress::Tick;

// Compare against the compact serializer without making a second copy.
// This also rejects duplicate keys collapsed by the parser and trailing data.
class CompactJsonMatch {
public:
    explicit CompactJsonMatch(std::string_view input) : _remaining(input) {}

    std::size_t write(std::uint8_t byte)
    {
        return write(&byte, 1);
    }

    std::size_t write(const std::uint8_t* bytes, std::size_t size)
    {
        if (!_matches || _remaining.substr(0, size) != std::string_view(reinterpret_cast<const char*>(bytes), size)) {
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

bool identifier(std::string_view value)
{
    return !value.empty() && value.size() <= NotificationController::max_id_bytes &&
           value.find('\0') == std::string_view::npos;
}

bool validUtf8(std::string_view input)
{
    while (!input.empty()) {
        const auto lead = static_cast<unsigned char>(input.front());
        if (lead < 0x80) {
            if (lead < 0x20) {
                return false;
            }
            input.remove_prefix(1);
            continue;
        }
        if (lead < 0xc2 || lead > 0xf4) {
            return false;
        }
        const std::size_t count = lead < 0xe0 ? 2 : lead < 0xf0 ? 3 : 4;
        if (input.size() < count) {
            return false;
        }
        const auto second = static_cast<unsigned char>(input[1]);
        if ((lead == 0xe0 && second < 0xa0) || (lead == 0xed && second >= 0xa0) ||
            (lead == 0xf0 && second < 0x90) || (lead == 0xf4 && second >= 0x90)) {
            return false;
        }
        if (!std::all_of(input.begin() + 1, input.begin() + count, [](unsigned char c) {
                return c >= 0x80 && c <= 0xbf;
            })) {
            return false;
        }
        input.remove_prefix(count);
    }
    return true;
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

std::optional<Tick> utcMillis(std::string_view value)
{
    if (value.size() != 24 || value[4] != '-' || value[7] != '-' || value[10] != 'T' ||
        value[13] != ':' || value[16] != ':' || value[19] != '.' || value[23] != 'Z') {
        return std::nullopt;
    }
    const int year = digits(value.substr(0, 4));
    const int month = digits(value.substr(5, 2));
    const int day = digits(value.substr(8, 2));
    const int hour = digits(value.substr(11, 2));
    const int minute = digits(value.substr(14, 2));
    const int second = digits(value.substr(17, 2));
    const int millis = digits(value.substr(20, 3));
    if (year < 1970 || month < 1 || month > 12 || day < 1 || hour < 0 || hour > 23 ||
        minute < 0 || minute > 59 || second < 0 || second > 59 || millis < 0) {
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

bool validPresentation(JsonObjectConst policy)
{
    return policy.size() == 4 && policy["ui"].is<bool>() && policy["audio"].is<bool>() &&
           policy["motion"].is<bool>() && policy["tts"].is<bool>();
}

bool validEvents(JsonArrayConst events)
{
    if (events.size() < 1 || events.size() > 100) {
        return false;
    }
    for (auto current = events.begin(); current != events.end(); ++current) {
        const auto id = stringValue(*current);
        if (id.empty() || id.find('\0') != std::string_view::npos) {
            return false;
        }
        for (auto previous = events.begin(); previous != current; ++previous) {
            if (stringValue(*previous) == id) {
                return false;
            }
        }
    }
    return true;
}

bool receiveIntent(
    DeviceStreamIngress& ingress, DeviceStreamIngress::Frame frame, JsonObjectConst envelope, Tick now)
{
    auto payload = envelope["payload"].as<JsonObjectConst>();
    const auto delivery = stringValue(envelope["delivery_id"]);
    const auto notification = stringValue(payload["notification_id"]);
    const auto expires = utcMillis(stringValue(payload["expires_at"]));
    const bool has_profile = !payload["presentation_profile"].isUnbound();
    const auto profile = payload["presentation_profile"].as<JsonString>();
    const auto profile_text = stringValue(payload["presentation_profile"]);
    const auto profile_length = std::count_if(profile_text.begin(), profile_text.end(), [](unsigned char c) {
        return (c & 0xc0) != 0x80;
    });
    if (payload.size() != (has_profile ? 11 : 10) ||
        (has_profile && !payload["presentation_profile"].isNull() &&
         (profile.isNull() || profile_length > 128)) ||
        !identifier(delivery) || notification.empty() || notification.find('\0') != std::string_view::npos ||
        !expires || *expires <= frame.sent_utc_ms ||
        stringValue(payload["schema_version"]) != "0.1" || stringValue(payload["delivery_id"]) != delivery ||
        stringValue(payload["device_id"]) != frame.device_id ||
        stringValue(payload["policy_version"]) != frame.policy_version ||
        !payload["generation"].is<std::uint64_t>() ||
        payload["generation"].as<std::uint64_t>() != frame.generation ||
        !payload["priority"].is<unsigned>() || payload["priority"].as<unsigned>() > 100 ||
        !validPresentation(payload["presentation_policy"].as<JsonObjectConst>()) ||
        !validEvents(payload["event_ids"].as<JsonArrayConst>())) {
        return false;
    }
    return ingress.receiveIntent(frame, delivery, *expires, now);
}
}  // namespace

bool receiveDeviceStreamJson(
    DeviceStreamIngress& ingress, DeviceStreamIngress::SessionId session,
    std::string_view json, std::size_t max_bytes, Tick now)
{
    if (json.empty() || json.size() > max_bytes || !validUtf8(json)) {
        return false;
    }
    JsonDocument document;
    if (deserializeJson(document, json.data(), json.size(), DeserializationOption::NestingLimit(4))) {
        return false;
    }
    CompactJsonMatch match(json);
    serializeJson(document, match);
    if (!match.complete()) {
        return false;
    }
    const auto envelope = document.as<JsonObjectConst>();
    const auto type = stringValue(envelope["type"]);
    const auto device = stringValue(envelope["device_id"]);
    const auto policy = stringValue(envelope["policy_version"]);
    const auto sent = utcMillis(stringValue(envelope["sent_at"]));
    if (!sent || !identifier(device) || !identifier(policy) || !identifier(stringValue(envelope["message_id"])) ||
        stringValue(envelope["schema_version"]) != "0.1" ||
        stringValue(envelope["direction"]) != "coordinator_to_device" ||
        !envelope["generation"].is<std::uint64_t>()) {
        return false;
    }

    DeviceStreamIngress::Frame frame{session, device, policy, envelope["generation"].as<std::uint64_t>(), *sent};
    if (type == "heartbeat" && envelope.size() == 8) {
        return ingress.receiveHeartbeat(frame, now);
    }
    return type == "notification.intent" && envelope.size() == 10 && receiveIntent(ingress, frame, envelope, now);
}

}  // namespace stackchan::notifications
