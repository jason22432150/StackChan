#include "policy_lease_http_client.h"

#include "coordinator_https.h"

#include <algorithm>

namespace stackchan::notifications {
namespace {
using Tick = NotificationController::Tick;

bool printableField(std::string_view text, std::size_t limit)
{
    return !text.empty() && text.size() <= limit &&
           std::all_of(text.begin(), text.end(), [](unsigned char c) {
               return c >= 0x21 && c <= 0x7e;
           });
}

}  // namespace

std::optional<PolicyLeaseBinding> PolicyLeaseHttpClient::fetch(const Config& config, Tick now_utc_ms)
{
    if (!printableField(config.device_id, NotificationController::max_id_bytes) ||
        !printableField(config.token, 512) || now_utc_ms == 0) {
        return std::nullopt;
    }

    const auto path = "/v1/devices/" + config.device_id + "/policy";
    const auto request = "GET " + path + " HTTP/1.1\r\nHost: " + config.coordinator_host +
                         "\r\nAuthorization: Bearer " + config.token +
                         "\r\nAccept: application/json\r\nConnection: close\r\n\r\n";
    const auto response = requestCoordinatorHttps(config.coordinator_host, config.port, config.coordinator_ca_pem,
                                                  request, config.max_response_bytes, config.network_timeout_ms);
    if (!response || response->status != 200) {
        return std::nullopt;
    }
    return parsePolicyLeaseJson(response->body, config.max_response_bytes, now_utc_ms);
}

}  // namespace stackchan::notifications
