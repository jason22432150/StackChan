#pragma once

#include "personal_pending_http_client.h"
#include "personal_pending_poll.h"

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace stackchan::notifications {

/**
 * 個人版 pending worker 參數（task 排程與 boot 組裝共用）。
 * 刻意不依賴 notification_product_runtime／esp_transport，方便 host CTest。
 */
struct PersonalPendingWorkerRequest {
    PersonalPendingHttpClient::Config http;
    std::uint64_t session = 1;
    std::string policy_version;
    std::uint64_t generation = 0;
    std::uint64_t policy_expires_utc_ms = 0;
    std::uint64_t fetch_interval_ms = kDefaultPersonalPendingFetchIntervalMs;
};

/**
 * 個人版啟動接線輸入（對齊 host `PersonalPendingBootConfig`）。
 * Token 存 NVS namespace `personal_pend`；需 `CONFIG_NVS_ENCRYPTION` 或
 * `CONFIG_STACKCHAN_PERSONAL_PENDING_CLEARTEXT_NVS`（明文 LAN 例外）；不進 Kconfig 字串。
 */
struct PersonalPendingBootConfig {
    std::string coordinator_host;
    std::uint16_t port = 8443;
    std::string device_id;
    std::string device_token;
    std::string policy_version{"pol_personal_v1"};
    std::uint64_t generation = 1;
    std::uint64_t session = 1;
    std::uint64_t policy_ttl_ms = 86'400'000;
    std::uint64_t fetch_interval_ms = kDefaultPersonalPendingFetchIntervalMs;
    std::string coordinator_ca_pem;  // 空 = cleartext
    int limit = 50;
};

std::optional<PersonalPendingWorkerRequest> buildPersonalPendingWorkerRequest(
    const PersonalPendingBootConfig& boot, std::uint64_t utc_ms);

bool requestPersonalPendingNotificationProduct(PersonalPendingWorkerRequest request);

bool schedulePersonalPendingBoot(const PersonalPendingBootConfig& boot, std::uint64_t utc_ms);

/**
 * 自 NVS `personal_pend` 讀取。
 * Fail-Closed：缺欄／無權限（無加密且未開 cleartext）→ nullopt。
 */
std::optional<PersonalPendingBootConfig> loadPersonalPendingBootConfigFromNvs();

/**
 * 寫入 NVS（佈建／測試）。Fail-Closed：無權限或欄位無效 → false。
 * cleartext 路徑僅限個人版 LAN 核准映像；host CTest 用 nvs_fakes 驗證。
 */
bool savePersonalPendingBootConfigToNvs(const PersonalPendingBootConfig& boot);

/** SNTP 後：NVS 有完整設定才排程。 */
bool trySchedulePersonalPendingBootAfterSntp();

/** 預設 = loadPersonalPendingBootConfigFromNvs（可測性覆寫點）。 */
std::optional<PersonalPendingBootConfig> loadPersonalPendingBootConfigForBoot();

}  // namespace stackchan::notifications
