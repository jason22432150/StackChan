#include "personal_pending_json.h"

#include "notification_payload.h"

#include <ArduinoJson.h>

namespace stackchan::notifications {
namespace {
using payload::CompactJsonMatch;
using payload::stringValue;
using payload::utcMillis;

bool validUtf8(std::string_view text)
{
    std::size_t i = 0;
    while (i < text.size()) {
        const auto lead = static_cast<unsigned char>(text[i]);
        std::size_t need = 0;
        if (lead <= 0x7f) {
            need = 1;
        } else if (lead >= 0xc2 && lead <= 0xdf) {
            need = 2;
        } else if (lead >= 0xe0 && lead <= 0xef) {
            need = 3;
        } else if (lead >= 0xf0 && lead <= 0xf4) {
            need = 4;
        } else {
            return false;
        }
        if (i + need > text.size()) {
            return false;
        }
        for (std::size_t j = 1; j < need; ++j) {
            if ((static_cast<unsigned char>(text[i + j]) & 0xc0) != 0x80) {
                return false;
            }
        }
        i += need;
    }
    return true;
}

bool identifier(std::string_view id)
{
    return !id.empty() && id.size() <= NotificationController::max_id_bytes &&
           id.find('\0') == std::string_view::npos;
}

bool validPresentation(JsonObjectConst policy)
{
    return policy.size() == 4 && policy["ui"].is<bool>() && policy["audio"].is<bool>() &&
           policy["motion"].is<bool>() && policy["tts"].is<bool>();
}
}  // namespace

std::size_t applyPersonalPendingJson(PersonalPendingIngress& ingress, std::string_view json,
                                     std::size_t max_bytes, PersonalPendingIngress::Tick now)
{
    if (json.empty() || json.size() > max_bytes || !validUtf8(json) || !ingress.bound()) {
        return 0;
    }
    JsonDocument document;
    if (deserializeJson(document, json.data(), json.size(), DeserializationOption::NestingLimit(4))) {
        return 0;
    }
    CompactJsonMatch match(json);
    serializeJson(document, match);
    if (!match.complete()) {
        return 0;
    }
    const auto root = document.as<JsonObjectConst>();
    if (root.size() != 2 || !root["items"].is<JsonArrayConst>() || !root["count"].is<unsigned>()) {
        return 0;
    }
    const auto items = root["items"].as<JsonArrayConst>();
    if (root["count"].as<unsigned>() != items.size() || items.size() > 100) {
        return 0;
    }
    std::size_t accepted = 0;
    for (JsonVariantConst entry : items) {
        if (!entry.is<JsonObjectConst>()) {
            continue;
        }
        const auto item = entry.as<JsonObjectConst>();
        const auto delivery = stringValue(item["delivery_id"]);
        const auto device = stringValue(item["device_id"]);
        const auto policy = stringValue(item["policy_version"]);
        const auto expires = utcMillis(stringValue(item["expires_at"]));
        const bool has_profile = !item["presentation_profile"].isUnbound();
        if (stringValue(item["schema_version"]) != "0.1" || !identifier(delivery) || !identifier(device) ||
            !identifier(policy) || !expires || !item["generation"].is<std::uint64_t>() ||
            !item["priority"].is<unsigned>() || item["priority"].as<unsigned>() > 100 ||
            !validPresentation(item["presentation_policy"].as<JsonObjectConst>()) ||
            (has_profile && !item["presentation_profile"].isNull() &&
             !item["presentation_profile"].is<const char*>())) {
            continue;
        }
        if (ingress.receiveItem(device, policy, item["generation"].as<std::uint64_t>(), delivery, *expires,
                                now)) {
            ++accepted;
        }
    }
    return accepted;
}

}  // namespace stackchan::notifications
