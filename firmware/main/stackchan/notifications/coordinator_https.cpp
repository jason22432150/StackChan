#include "coordinator_https.h"

#include "coordinator_http_io.h"

#include <esp_transport.h>
#include <esp_transport_ssl.h>
#include <limits>
#include <memory>
#include <new>
#include <type_traits>

namespace stackchan::notifications {

std::optional<CoordinatorHttpsResponse> requestCoordinatorHttps(
    const std::string& host, std::uint16_t port, const std::string& ca_pem, const std::string& request,
    std::size_t max_response_bytes, int timeout_ms)
{
    constexpr auto max_int = static_cast<std::size_t>(std::numeric_limits<int>::max());
    if (!http_io::validHost(host) || port == 0 || !ca_pem.starts_with("-----BEGIN CERTIFICATE-----") ||
        ca_pem.size() >= max_int || ca_pem.find('\0') != std::string::npos || timeout_ms <= 0 ||
        max_response_bytes == 0 || max_response_bytes > max_int || request.empty() ||
        request.size() > max_response_bytes || request.size() >= max_int) {
        return std::nullopt;
    }

    const auto release = [](esp_transport_handle_t handle) {
        esp_transport_close(handle);
        esp_transport_destroy(handle);
    };
    std::unique_ptr<std::remove_pointer_t<esp_transport_handle_t>, decltype(release)> tls(
        esp_transport_ssl_init(), release);
    if (!tls) {
        return std::nullopt;
    }
    esp_transport_ssl_set_cert_data(tls.get(), ca_pem.c_str(), static_cast<int>(ca_pem.size()));
    if (esp_transport_connect(tls.get(), host.c_str(), port, timeout_ms) != 0) {
        return std::nullopt;
    }
    return http_io::exchange(tls.get(), request, max_response_bytes, timeout_ms);
}

}  // namespace stackchan::notifications
