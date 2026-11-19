#pragma once

#include "coordinator_https.h"

#include <esp_transport.h>

#include <cstddef>
#include <string>
#include <string_view>

namespace stackchan::notifications::http_io {

bool validHost(std::string_view host);

/**
 * 已 connect 的 transport：寫入 request 並依 Content-Length 讀完整回應。
 * 拒 redirect／Transfer-Encoding；失敗回 nullopt。
 */
std::optional<CoordinatorHttpsResponse> exchange(
    esp_transport_handle_t transport, const std::string& request, std::size_t max_response_bytes,
    int timeout_ms);

}  // namespace stackchan::notifications::http_io
