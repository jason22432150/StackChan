#include "policy_lease_http_client.h"

#include <algorithm>
#include <cctype>
#include <cstring>
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

int parseStatus(std::string_view status_line)
{
    // HTTP/1.1 200 OK
    if (status_line.size() < 12 || status_line.substr(0, 9) != "HTTP/1.1 ") {
        return -1;
    }
    int status = 0;
    for (char c : status_line.substr(9, 3)) {
        if (c < '0' || c > '9') {
            return -1;
        }
        status = status * 10 + (c - '0');
    }
    return status;
}

bool headerHasLocation(std::string_view headers)
{
    auto remaining = headers;
    while (!remaining.empty()) {
        const auto end = remaining.find("\r\n");
        const auto line = end == std::string_view::npos ? remaining : remaining.substr(0, end);
        if (line.size() >= 9) {
            auto name = line.substr(0, 8);
            if ((name[0] == 'L' || name[0] == 'l') && (name[1] == 'o' || name[1] == 'O') &&
                (name[2] == 'c' || name[2] == 'C') && (name[3] == 'a' || name[3] == 'A') &&
                (name[4] == 't' || name[4] == 'T') && (name[5] == 'i' || name[5] == 'I') &&
                (name[6] == 'o' || name[6] == 'O') && (name[7] == 'n' || name[7] == 'N') &&
                line[8] == ':') {
                return true;
            }
        }
        if (end == std::string_view::npos) {
            break;
        }
        remaining.remove_prefix(end + 2);
    }
    return false;
}

std::optional<std::size_t> contentLength(std::string_view headers)
{
    auto remaining = headers;
    while (!remaining.empty()) {
        const auto end = remaining.find("\r\n");
        const auto line = end == std::string_view::npos ? remaining : remaining.substr(0, end);
        constexpr std::string_view key = "content-length:";
        if (line.size() >= key.size()) {
            bool match = true;
            for (std::size_t i = 0; i < key.size(); ++i) {
                const auto expected = key[i];
                const auto actual = static_cast<char>(std::tolower(static_cast<unsigned char>(line[i])));
                if (actual != expected) {
                    match = false;
                    break;
                }
            }
            if (match) {
                auto value = line.substr(key.size());
                while (!value.empty() && value.front() == ' ') {
                    value.remove_prefix(1);
                }
                if (value.empty()) {
                    return std::nullopt;
                }
                std::size_t length = 0;
                for (char c : value) {
                    if (c < '0' || c > '9') {
                        return std::nullopt;
                    }
                    length = length * 10 + static_cast<std::size_t>(c - '0');
                }
                return length;
            }
        }
        if (end == std::string_view::npos) {
            break;
        }
        remaining.remove_prefix(end + 2);
    }
    return std::nullopt;
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
    const auto status_line = status_end == std::string_view::npos ? headers : headers.substr(0, status_end);
    const auto status = parseStatus(status_line);
    if (status != 200 || headerHasLocation(headers)) {
        return std::nullopt;
    }
    const auto body = response.substr(header_end + 4);
    const auto length = contentLength(headers);
    if (!length || *length != body.size() || *length > config.max_response_bytes) {
        return std::nullopt;
    }
    return parsePolicyLeaseJson(body, *length, now_utc_ms);
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
