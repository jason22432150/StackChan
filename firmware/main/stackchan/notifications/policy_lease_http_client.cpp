#include "policy_lease_http_client.h"

#include <algorithm>
#include <charconv>
#include <cctype>
#include <esp_transport.h>
#include <esp_transport_ssl.h>
#include <limits>
#include <memory>
#include <new>

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

bool validHost(std::string_view host)
{
    return !host.empty() && host.size() <= 253 &&
           std::all_of(host.begin(), host.end(), [](unsigned char c) {
               return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
                      c == '.' || c == '-';
           });
}

bool headerNameIs(std::string_view name, std::string_view lowercase_name)
{
    return std::equal(name.begin(), name.end(), lowercase_name.begin(), lowercase_name.end(),
                      [](unsigned char byte, char expected) { return std::tolower(byte) == expected; });
}

std::optional<std::size_t> contentLength(std::string_view headers)
{
    std::optional<std::size_t> length;
    while (!headers.empty()) {
        const auto end = headers.find("\r\n");
        const auto line = headers.substr(0, end);
        const auto colon = line.find(':');
        const auto name = line.substr(0, colon);
        constexpr std::string_view token_chars =
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!#$%&'*+-.^`_|~";
        if (line.find_first_of("\r\n") != std::string_view::npos ||
            colon == std::string_view::npos || name.empty() ||
            name.find_first_not_of(token_chars) != std::string_view::npos ||
            headerNameIs(name, "location") || headerNameIs(name, "transfer-encoding")) {
            return std::nullopt;
        }
        if (headerNameIs(name, "content-length")) {
            const auto field = line.substr(colon + 1);
            const auto first = field.find_first_not_of(" \t");
            if (length || first == std::string_view::npos) {
                return std::nullopt;
            }
            const auto last = field.find_last_not_of(" \t");
            std::size_t parsed = 0;
            const auto end_of_value = field.data() + last + 1;
            const auto result = std::from_chars(field.data() + first, end_of_value, parsed);
            if (result.ec != std::errc{} || result.ptr != end_of_value) {
                return std::nullopt;
            }
            length = parsed;
        }
        if (end == std::string_view::npos) {
            break;
        }
        headers.remove_prefix(end + 2);
    }
    return length;
}
}  // namespace

std::optional<PolicyLeaseBinding> PolicyLeaseHttpClient::fetch(const Config& config, Tick now_utc_ms)
{
    constexpr auto max_int = static_cast<std::size_t>(std::numeric_limits<int>::max());
    if (!validHost(config.coordinator_host) || config.port == 0 ||
        !config.coordinator_ca_pem.starts_with("-----BEGIN CERTIFICATE-----") ||
        config.coordinator_ca_pem.size() >= max_int ||
        config.coordinator_ca_pem.find('\0') != std::string::npos ||
        !printableField(config.device_id, NotificationController::max_id_bytes) ||
        !printableField(config.token, 512) || config.network_timeout_ms <= 0 ||
        config.max_response_bytes == 0 || config.max_response_bytes > max_int || now_utc_ms == 0) {
        return std::nullopt;
    }

    const auto path = "/v1/devices/" + config.device_id + "/policy";
    const auto request = "GET " + path + " HTTP/1.1\r\nHost: " + config.coordinator_host +
                         "\r\nAuthorization: Bearer " + config.token +
                         "\r\nAccept: application/json\r\nConnection: close\r\n\r\n";
    if (request.size() > config.max_response_bytes || request.size() >= max_int) {
        return std::nullopt;
    }

    auto buffer = std::unique_ptr<char[]>(new (std::nothrow) char[config.max_response_bytes]);
    if (!buffer) {
        return std::nullopt;
    }

    auto* tls = esp_transport_ssl_init();
    if (!tls) {
        return std::nullopt;
    }
    esp_transport_ssl_set_cert_data(
        tls, config.coordinator_ca_pem.c_str(), static_cast<int>(config.coordinator_ca_pem.size()));
    if (esp_transport_connect(
            tls, config.coordinator_host.c_str(), config.port, config.network_timeout_ms) != 0) {
        esp_transport_close(tls);
        esp_transport_destroy(tls);
        return std::nullopt;
    }

    const int written = esp_transport_write(
        tls, request.c_str(), static_cast<int>(request.size()), config.network_timeout_ms);
    if (written != static_cast<int>(request.size())) {
        esp_transport_close(tls);
        esp_transport_destroy(tls);
        return std::nullopt;
    }

    std::size_t received = 0;
    while (received < config.max_response_bytes) {
        const int count = esp_transport_read(
            tls, buffer.get() + received,
            static_cast<int>(config.max_response_bytes - received), config.network_timeout_ms);
        if (count < 0) {
            esp_transport_close(tls);
            esp_transport_destroy(tls);
            return std::nullopt;
        }
        if (count == 0) {
            break;
        }
        received += static_cast<std::size_t>(count);
    }
    esp_transport_close(tls);
    esp_transport_destroy(tls);

    const std::string_view response(buffer.get(), received);
    const auto header_end = response.find("\r\n\r\n");
    if (header_end == std::string_view::npos || header_end < 12) {
        return std::nullopt;
    }
    const auto headers = response.substr(0, header_end);
    const auto status_end = headers.find("\r\n");
    const auto status_line = headers.substr(0, status_end);
    if (status_end == std::string_view::npos || !status_line.starts_with("HTTP/1.1 200 ") ||
        status_line.find_first_of("\r\n") != std::string_view::npos) {
        return std::nullopt;
    }
    const auto body = response.substr(header_end + 4);
    const auto length = contentLength(headers.substr(status_end + 2));
    if (!length || *length != body.size() || *length > config.max_response_bytes) {
        return std::nullopt;
    }
    return parsePolicyLeaseJson(body, *length, now_utc_ms);
}

}  // namespace stackchan::notifications
