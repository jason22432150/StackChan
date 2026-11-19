#include "personal_pending_http_client.h"

#include "coordinator_https.h"

#include <algorithm>
#include <charconv>

namespace stackchan::notifications {
namespace {
bool printableField(std::string_view text, std::size_t limit)
{
    return !text.empty() && text.size() <= limit &&
           std::all_of(text.begin(), text.end(), [](unsigned char c) { return c >= 0x21 && c <= 0x7e; });
}
}  // namespace

std::optional<PersonalPendingHttpClient::Result> PersonalPendingHttpClient::fetch(const Config& config)
{
    if (!printableField(config.device_id, NotificationController::max_id_bytes) ||
        !printableField(config.token, 512) || config.limit < 1 || config.limit > 100 ||
        config.max_response_bytes == 0 || config.network_timeout_ms <= 0) {
        return std::nullopt;
    }

    char limit_buf[8];
    const auto* limit_end =
        std::to_chars(limit_buf, limit_buf + sizeof(limit_buf), config.limit).ptr;
    const std::string_view limit_text(limit_buf, static_cast<std::size_t>(limit_end - limit_buf));

    const auto path = "/v1/devices/" + config.device_id + "/notifications/pending?limit=" +
                      std::string(limit_text);
    const auto request = "GET " + path + " HTTP/1.1\r\nHost: " + config.coordinator_host +
                         "\r\nAuthorization: Bearer " + config.token +
                         "\r\nAccept: application/json\r\nUser-Agent: stackchan-cores3-pending/0.1\r\n"
                         "Connection: close\r\n\r\n";

    std::optional<CoordinatorHttpsResponse> response;
    if (config.coordinator_ca_pem.empty()) {
        response = requestCoordinatorHttp(config.coordinator_host, config.port, request,
                                          config.max_response_bytes, config.network_timeout_ms);
    } else {
        response = requestCoordinatorHttps(config.coordinator_host, config.port, config.coordinator_ca_pem,
                                           request, config.max_response_bytes, config.network_timeout_ms);
    }
    if (!response || response->status != 200) {
        return std::nullopt;
    }
    return Result{std::move(response->body)};
}

bool PersonalPendingHttpClient::ack(const Config& config, std::string_view delivery_id)
{
    if (!printableField(config.device_id, NotificationController::max_id_bytes) ||
        !printableField(config.token, 512) ||
        !printableField(delivery_id, NotificationController::max_id_bytes) ||
        config.max_response_bytes == 0 || config.network_timeout_ms <= 0) {
        return false;
    }

    const auto path = "/v1/devices/" + config.device_id + "/notifications/pending/" +
                      std::string(delivery_id) + "/ack";
    const auto request = "POST " + path + " HTTP/1.1\r\nHost: " + config.coordinator_host +
                         "\r\nAuthorization: Bearer " + config.token +
                         "\r\nAccept: application/json\r\nContent-Length: 0\r\n"
                         "User-Agent: stackchan-cores3-pending/0.1\r\n"
                         "Connection: close\r\n\r\n";

    std::optional<CoordinatorHttpsResponse> response;
    if (config.coordinator_ca_pem.empty()) {
        response = requestCoordinatorHttp(config.coordinator_host, config.port, request,
                                          config.max_response_bytes, config.network_timeout_ms);
    } else {
        response = requestCoordinatorHttps(config.coordinator_host, config.port, config.coordinator_ca_pem,
                                           request, config.max_response_bytes, config.network_timeout_ms);
    }
    // 200 且 body 含 "acked":true（含 duplicate）即視為佇列可自 pull 移除。
    return response.has_value() && response->status == 200 &&
           response->body.find("\"acked\":true") != std::string::npos;
}

}  // namespace stackchan::notifications
