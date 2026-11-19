#include "coordinator_https.h"

#include "coordinator_http_io.h"

#include <esp_transport.h>
#include <esp_transport_tcp.h>
#include <limits>
#include <memory>
#include <new>
#include <type_traits>

namespace stackchan::notifications {

std::optional<CoordinatorHttpsResponse> requestCoordinatorHttp(const std::string& host, std::uint16_t port,
                                                               const std::string& request,
                                                               std::size_t max_response_bytes, int timeout_ms)
{
    constexpr auto max_int = static_cast<std::size_t>(std::numeric_limits<int>::max());
    if (!http_io::validHost(host) || port == 0 || timeout_ms <= 0 || max_response_bytes == 0 ||
        max_response_bytes > max_int || request.empty() || request.size() > max_response_bytes ||
        request.size() >= max_int) {
        return std::nullopt;
    }

    const auto release = [](esp_transport_handle_t handle) {
        esp_transport_close(handle);
        esp_transport_destroy(handle);
    };
    // 個人版 LAN cleartext；production 應改走 requestCoordinatorHttps。
    std::unique_ptr<std::remove_pointer_t<esp_transport_handle_t>, decltype(release)> tcp(
        esp_transport_tcp_init(), release);
    if (!tcp) {
        return std::nullopt;
    }
    if (esp_transport_connect(tcp.get(), host.c_str(), port, timeout_ms) != 0) {
        return std::nullopt;
    }
    return http_io::exchange(tcp.get(), request, max_response_bytes, timeout_ms);
}

}  // namespace stackchan::notifications
