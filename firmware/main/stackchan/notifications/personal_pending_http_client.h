#pragma once

#include "notification_controller.h"

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace stackchan::notifications {

/**
 * CoreS3 → Pi：`GET /v1/devices/{id}/notifications/pending`。
 *
 * - `coordinator_ca_pem` 空：cleartext HTTP（個人 LAN）
 * - 非空：HTTPS + 明確 CA（須以 -----BEGIN CERTIFICATE----- 開頭）
 * 不 present、不 enqueue；成功僅回傳 200 body 供 feedPersonalPending…。
 */
class PersonalPendingHttpClient {
public:
    struct Config {
        std::string coordinator_host;
        std::uint16_t port = 0;
        std::string coordinator_ca_pem;  // 空 = cleartext
        std::string token;
        std::string device_id;
        std::size_t max_response_bytes = 4096;
        int network_timeout_ms = 10'000;
        int limit = 50;
    };

    struct Result {
        std::string body;
    };

    std::optional<Result> fetch(const Config& config);
};

}  // namespace stackchan::notifications
