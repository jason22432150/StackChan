#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace stackchan::notifications {

struct CoordinatorHttpsResponse {
    int status = 0;
    std::string body;
    std::string pairing_claim;
};

// The request must be assembled by the caller from validated fields.
std::optional<CoordinatorHttpsResponse> requestCoordinatorHttps(
    const std::string& host, std::uint16_t port, const std::string& ca_pem,
    const std::string& request, std::size_t max_response_bytes, int timeout_ms);

/**
 * 個人版 LAN cleartext（無 TLS）。契約與 HTTPS 相同：拒 redirect、依 Content-Length 讀完。
 * Production／不可信網路請改用 requestCoordinatorHttps。
 */
std::optional<CoordinatorHttpsResponse> requestCoordinatorHttp(
    const std::string& host, std::uint16_t port, const std::string& request,
    std::size_t max_response_bytes, int timeout_ms);

}  // namespace stackchan::notifications

