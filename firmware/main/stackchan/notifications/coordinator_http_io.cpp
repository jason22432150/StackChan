#include "coordinator_http_io.h"

#include <algorithm>
#include <cctype>
#include <charconv>
#include <limits>
#include <memory>
#include <new>

namespace stackchan::notifications::http_io {
namespace {
bool headerNameIs(std::string_view name, std::string_view lowercase_name)
{
    return std::equal(name.begin(), name.end(), lowercase_name.begin(), lowercase_name.end(),
                      [](unsigned char byte, char expected) { return std::tolower(byte) == expected; });
}

std::optional<std::size_t> parseHeaders(std::string_view headers, std::string& pairing_claim)
{
    std::optional<std::size_t> length;
    while (!headers.empty()) {
        const auto end = headers.find("\r\n");
        const auto line = headers.substr(0, end);
        const auto colon = line.find(':');
        const auto name = line.substr(0, colon);
        constexpr std::string_view token_chars =
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!#$%&'*+-.^`_|~";
        if (line.find_first_of("\r\n") != std::string_view::npos || colon == std::string_view::npos ||
            name.empty() || name.find_first_not_of(token_chars) != std::string_view::npos ||
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
        if (headerNameIs(name, "x-stackchan-pairing-claim")) {
            const auto field = line.substr(colon + 1);
            const auto first = field.find_first_not_of(" \t");
            if (!pairing_claim.empty() || first == std::string_view::npos) {
                return std::nullopt;
            }
            pairing_claim.assign(field.substr(first, field.find_last_not_of(" \t") - first + 1));
        }
        if (end == std::string_view::npos) {
            break;
        }
        headers.remove_prefix(end + 2);
    }
    return length;
}

std::optional<std::size_t> parseResponseHeader(std::string_view headers, CoordinatorHttpsResponse& result)
{
    const auto status_end = headers.find("\r\n");
    const auto status_line = headers.substr(0, status_end);
    // Pi BaseHTTP／多數簡單 LAN server 回 HTTP/1.0；與 1.1 同長度 status 前綴。
    const bool http_1x = status_line.starts_with("HTTP/1.1 ") || status_line.starts_with("HTTP/1.0 ");
    if (status_end == std::string_view::npos || !http_1x || status_line.size() < 13 ||
        status_line[12] != ' ' || status_line.find_first_of("\r\n") != std::string_view::npos) {
        return std::nullopt;
    }
    const auto* status_start = status_line.data() + 9;
    const auto status = std::from_chars(status_start, status_start + 3, result.status);
    if (status.ec != std::errc{} || status.ptr != status_start + 3 || result.status < 100) {
        return std::nullopt;
    }
    return parseHeaders(headers.substr(status_end + 2), result.pairing_claim);
}
}  // namespace

bool validHost(std::string_view host)
{
    return !host.empty() && host.size() <= 253 &&
           std::all_of(host.begin(), host.end(), [](unsigned char c) {
               return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
                      c == '.' || c == '-';
           });
}

std::optional<CoordinatorHttpsResponse> exchange(esp_transport_handle_t transport, const std::string& request,
                                                 std::size_t max_response_bytes, int timeout_ms)
{
    if (!transport || request.empty() || max_response_bytes == 0 || timeout_ms <= 0) {
        return std::nullopt;
    }
    auto buffer = std::unique_ptr<char[]>(new (std::nothrow) char[max_response_bytes]);
    if (!buffer) {
        return std::nullopt;
    }
    if (esp_transport_write(transport, request.c_str(), static_cast<int>(request.size()), timeout_ms) !=
        static_cast<int>(request.size())) {
        return std::nullopt;
    }

    CoordinatorHttpsResponse result;
    std::size_t received = 0;
    std::size_t body_offset = 0;
    std::size_t expected = 0;
    while (received < max_response_bytes) {
        const auto remaining = max_response_bytes - received;
        const int count = esp_transport_read(transport, buffer.get() + received, static_cast<int>(remaining),
                                             timeout_ms);
        if (count <= 0 || static_cast<std::size_t>(count) > remaining) {
            return std::nullopt;
        }
        received += static_cast<std::size_t>(count);
        const std::string_view response(buffer.get(), received);
        if (body_offset == 0) {
            const auto header_end = response.find("\r\n\r\n");
            if (header_end == std::string_view::npos) {
                continue;
            }
            body_offset = header_end + 4;
            const auto length = parseResponseHeader(response.substr(0, header_end), result);
            if (!length || *length > max_response_bytes - body_offset) {
                return std::nullopt;
            }
            expected = body_offset + *length;
        }
        if (received > expected) {
            return std::nullopt;
        }
        if (received == expected) {
            result.body.assign(response.substr(body_offset));
            return result;
        }
    }
    return std::nullopt;
}

}  // namespace stackchan::notifications::http_io
