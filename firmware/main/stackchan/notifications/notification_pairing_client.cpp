#include "notification_pairing_client.h"

#include "coordinator_https.h"
#include "notification_payload.h"
#include "notification_utc_clock.h"

#include <utility>

namespace stackchan::notifications {
namespace {
constexpr std::string_view pairing_path = "/v1/pairing/sessions";
constexpr std::string_view start_body =
    R"({"schema_version":"0.1","subject_type":"device","display_name":"CoreS3"})";

bool validPairingId(std::string_view id)
{
    return id.size() == 21 && id.starts_with("pair_") &&
           id.substr(5).find_first_not_of("0123456789abcdef") == std::string_view::npos;
}

bool validClaim(std::string_view claim)
{
    return claim.size() >= 32 && claim.size() <= 128 &&
           claim.find_first_not_of(
               "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_") == std::string_view::npos;
}

std::string post(std::string_view path, const NotificationPairingEndpoint& endpoint)
{
    return "POST " + std::string(path) + " HTTP/1.1\r\nHost: " + endpoint.coordinator_host +
           "\r\nContent-Type: application/json\r\nAccept: application/json\r\nConnection: close\r\n";
}

std::optional<CoordinatorHttpsResponse> sendPairingRequest(const NotificationPairingEndpoint& endpoint,
                                                           const std::string& request)
{
    return requestCoordinatorHttps(endpoint.coordinator_host, endpoint.port, endpoint.coordinator_ca_pem, request,
                                   kCoreS3MvpRuntimeProfile.max_frame_bytes,
                                   kCoreS3MvpRuntimeProfile.network_timeout_ms);
}
}  // namespace

std::optional<std::string> NotificationPairingClient::start(NotificationPairingEndpoint endpoint, std::uint16_t stream_port)
{
    cancel();
    if (notificationUtcMs() == 0 || stream_port == 0 || endpoint.coordinator_host.size() > 253 ||
        endpoint.coordinator_ca_pem.size() > 3999) {
        return std::nullopt;
    }
    const auto response = sendPairingRequest(endpoint, post(pairing_path, endpoint) + "Content-Length: " +
                                             std::to_string(start_body.size()) + "\r\n\r\n" + std::string(start_body));
    if (!response || response->status != 200 || !validClaim(response->pairing_claim)) {
        return std::nullopt;
    }
    JsonDocument document;
    if (deserializeJson(document, response->body, DeserializationOption::NestingLimit(2))) {
        return std::nullopt;
    }
    payload::CompactJsonMatch match(response->body);
    serializeJson(document, match);
    const auto challenge = document.as<JsonObjectConst>();
    const auto id = payload::stringValue(challenge["pairing_id"]);
    const auto code = payload::stringValue(challenge["user_code"]);
    const auto expiry = payload::stringValue(challenge["expires_at"]);
    const auto expires_at = payload::utcMillis(expiry);
    if (!match.complete() || challenge.size() != 5 || payload::stringValue(challenge["schema_version"]) != "0.1" ||
        payload::stringValue(challenge["subject_type"]) != "device" || !validPairingId(id) || !expires_at ||
        code.size() != 6 || code.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") != std::string_view::npos ||
        !beginNotificationProductPairing(id, expiry, {endpoint.coordinator_host, stream_port, endpoint.coordinator_ca_pem})) {
        return std::nullopt;
    }
    _pairing_id.assign(id);
    _claim = response->pairing_claim;
    _endpoint = std::move(endpoint);
    _expires_at = *expires_at;
    return std::string(code);
}

NotificationPairingClient::Completion NotificationPairingClient::complete()
{
    const auto now = notificationUtcMs();
    if (_pairing_id.empty() || now == 0 || now >= _expires_at) {
        cancel();
        return Completion::Unavailable;
    }
    const auto path = std::string(pairing_path) + "/" + _pairing_id + "/complete";
    const auto response = sendPairingRequest(
        _endpoint, post(path, _endpoint) + "X-StackChan-Pairing-Claim: " + _claim + "\r\nContent-Length: 0\r\n\r\n");
    const auto after_request = notificationUtcMs();
    if (response && response->status == 403 && after_request >= now && after_request < _expires_at) {
        return Completion::Pending;
    }
    const bool delivered = response && response->status == 200 && after_request >= now &&
                           finishNotificationProductPairing(_pairing_id, response->body);
    cancel();
    return delivered ? Completion::Delivered : Completion::Unavailable;
}

void NotificationPairingClient::cancel()
{
    if (!_pairing_id.empty()) {
        (void)finishNotificationProductPairing(_pairing_id, {});
    }
    _pairing_id.clear();
    _claim.clear();
    _endpoint = {};
    _expires_at = 0;
}

}  // namespace stackchan::notifications
