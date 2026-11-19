#include "personal_pending_boot.h"

#include "notification_controller.h"

#include <algorithm>
#include <limits>
#include <nvs.h>
#include <sdkconfig.h>

namespace stackchan::notifications {
std::uint64_t notificationUtcMs() noexcept;

namespace {
constexpr const char* kNvsNamespace = "personal_pend";

// 加密 NVS，或個人版明確允許的 cleartext NVS；否則 Fail-Closed。
#if (defined(CONFIG_NVS_ENCRYPTION) && CONFIG_NVS_ENCRYPTION) ||               \
    (defined(CONFIG_STACKCHAN_PERSONAL_PENDING_CLEARTEXT_NVS) &&               \
     CONFIG_STACKCHAN_PERSONAL_PENDING_CLEARTEXT_NVS)
#define STACKCHAN_PERSONAL_PEND_NVS_STORAGE 1
#else
#define STACKCHAN_PERSONAL_PEND_NVS_STORAGE 0
#endif

bool printableField(std::string_view text, std::size_t limit)
{
    return !text.empty() && text.size() <= limit &&
           std::all_of(text.begin(), text.end(), [](unsigned char c) { return c >= 0x21 && c <= 0x7e; });
}

bool validHost(std::string_view host)
{
    return !host.empty() && host.size() <= 253 &&
           std::all_of(host.begin(), host.end(), [](unsigned char c) {
               return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
                      c == '.' || c == '-';
           });
}

bool validBootFields(const PersonalPendingBootConfig& boot)
{
    if (boot.session == 0 || boot.port == 0 || boot.policy_ttl_ms == 0 || boot.fetch_interval_ms < 1000 ||
        boot.limit < 1 || boot.limit > 100 || !validHost(boot.coordinator_host) ||
        !printableField(boot.device_id, NotificationController::max_id_bytes) ||
        !printableField(boot.device_token, 512) || boot.device_token.size() < 16 ||
        !printableField(boot.policy_version, NotificationController::max_id_bytes)) {
        return false;
    }
    if (!boot.coordinator_ca_pem.empty() &&
        (!boot.coordinator_ca_pem.starts_with("-----BEGIN CERTIFICATE-----") ||
         boot.coordinator_ca_pem.size() > 3999 ||
         boot.coordinator_ca_pem.find('\0') != std::string::npos)) {
        return false;
    }
    return true;
}

#if STACKCHAN_PERSONAL_PEND_NVS_STORAGE
struct NvsHandle {
    nvs_handle_t value;
    ~NvsHandle() { nvs_close(value); }
};

bool readString(nvs_handle_t handle, const char* key, std::size_t max_bytes, std::string& out)
{
    std::size_t size = 0;
    if (nvs_get_str(handle, key, nullptr, &size) != ESP_OK || size < 2 || size > max_bytes + 1) {
        return false;
    }
    out.resize(size);
    if (nvs_get_str(handle, key, out.data(), &size) != ESP_OK || size != out.size() ||
        out.find('\0') != out.size() - 1) {
        return false;
    }
    out.pop_back();
    return true;
}

bool writeString(nvs_handle_t handle, const char* key, std::string_view value)
{
    return nvs_set_str(handle, key, std::string(value).c_str()) == ESP_OK;
}
#endif
}  // namespace

std::optional<PersonalPendingWorkerRequest> buildPersonalPendingWorkerRequest(
    const PersonalPendingBootConfig& boot, std::uint64_t utc_ms)
{
    if (utc_ms == 0 || !validBootFields(boot) ||
        boot.policy_ttl_ms > std::numeric_limits<std::uint64_t>::max() - utc_ms) {
        return std::nullopt;
    }

    PersonalPendingWorkerRequest request;
    request.http.coordinator_host = boot.coordinator_host;
    request.http.port = boot.port;
    request.http.coordinator_ca_pem = boot.coordinator_ca_pem;
    request.http.token = boot.device_token;
    request.http.device_id = boot.device_id;
    request.http.max_response_bytes = 4096;
    request.http.network_timeout_ms = 10'000;
    request.http.limit = boot.limit;
    request.session = boot.session;
    request.policy_version = boot.policy_version;
    request.generation = boot.generation;
    request.policy_expires_utc_ms = utc_ms + boot.policy_ttl_ms;
    request.fetch_interval_ms = boot.fetch_interval_ms;
    return request;
}

bool schedulePersonalPendingBoot(const PersonalPendingBootConfig& boot, std::uint64_t utc_ms)
{
    auto request = buildPersonalPendingWorkerRequest(boot, utc_ms);
    if (!request) {
        return false;
    }
    return requestPersonalPendingNotificationProduct(std::move(*request));
}

std::optional<PersonalPendingBootConfig> loadPersonalPendingBootConfigFromNvs()
{
#if !STACKCHAN_PERSONAL_PEND_NVS_STORAGE
    return std::nullopt;
#else
    nvs_handle_t raw_handle;
    if (nvs_open(kNvsNamespace, NVS_READONLY, &raw_handle) != ESP_OK) {
        return std::nullopt;
    }
    const NvsHandle handle{raw_handle};
    PersonalPendingBootConfig boot;
    std::uint16_t port = 0;
    std::uint16_t generation = 0;
    std::uint16_t session = 0;
    std::uint16_t limit = 0;
    std::uint32_t ttl_sec = 0;
    std::uint32_t fetch_ms = 0;
    if (nvs_get_u16(handle.value, "port", &port) != ESP_OK || port == 0 ||
        nvs_get_u16(handle.value, "generation", &generation) != ESP_OK ||
        nvs_get_u16(handle.value, "session", &session) != ESP_OK || session == 0 ||
        nvs_get_u16(handle.value, "limit", &limit) != ESP_OK ||
        nvs_get_u32(handle.value, "ttl_sec", &ttl_sec) != ESP_OK || ttl_sec == 0 ||
        nvs_get_u32(handle.value, "fetch_ms", &fetch_ms) != ESP_OK || fetch_ms < 1000 ||
        !readString(handle.value, "host", 253, boot.coordinator_host) ||
        !readString(handle.value, "device_id", NotificationController::max_id_bytes, boot.device_id) ||
        !readString(handle.value, "token", 512, boot.device_token) ||
        !readString(handle.value, "policy_ver", NotificationController::max_id_bytes, boot.policy_version)) {
        return std::nullopt;
    }
    // ca_pem 可缺省（HTTP cleartext）
    std::string ca;
    if (readString(handle.value, "ca_pem", 3999, ca)) {
        boot.coordinator_ca_pem = std::move(ca);
    }
    boot.port = port;
    boot.generation = generation;
    boot.session = session;
    boot.limit = static_cast<int>(limit);
    boot.policy_ttl_ms = static_cast<std::uint64_t>(ttl_sec) * 1000ULL;
    boot.fetch_interval_ms = fetch_ms;
    if (!validBootFields(boot)) {
        return std::nullopt;
    }
    return boot;
#endif
}

bool savePersonalPendingBootConfigToNvs(const PersonalPendingBootConfig& boot)
{
#if !STACKCHAN_PERSONAL_PEND_NVS_STORAGE
    (void)boot;
    return false;
#else
    if (!validBootFields(boot) || boot.policy_ttl_ms % 1000 != 0 ||
        boot.policy_ttl_ms / 1000 > std::numeric_limits<std::uint32_t>::max() ||
        boot.generation > std::numeric_limits<std::uint16_t>::max() ||
        boot.session > std::numeric_limits<std::uint16_t>::max() ||
        boot.fetch_interval_ms > std::numeric_limits<std::uint32_t>::max()) {
        return false;
    }
    nvs_handle_t raw_handle;
    if (nvs_open(kNvsNamespace, NVS_READWRITE, &raw_handle) != ESP_OK) {
        return false;
    }
    const NvsHandle handle{raw_handle};
    const auto ttl_sec = static_cast<std::uint32_t>(boot.policy_ttl_ms / 1000);
    if (nvs_set_u16(handle.value, "port", boot.port) != ESP_OK ||
        nvs_set_u16(handle.value, "generation", static_cast<std::uint16_t>(boot.generation)) != ESP_OK ||
        nvs_set_u16(handle.value, "session", static_cast<std::uint16_t>(boot.session)) != ESP_OK ||
        nvs_set_u16(handle.value, "limit", static_cast<std::uint16_t>(boot.limit)) != ESP_OK ||
        nvs_set_u32(handle.value, "ttl_sec", ttl_sec) != ESP_OK ||
        nvs_set_u32(handle.value, "fetch_ms", static_cast<std::uint32_t>(boot.fetch_interval_ms)) != ESP_OK ||
        !writeString(handle.value, "host", boot.coordinator_host) ||
        !writeString(handle.value, "device_id", boot.device_id) ||
        !writeString(handle.value, "token", boot.device_token) ||
        !writeString(handle.value, "policy_ver", boot.policy_version)) {
        return false;
    }
    if (!boot.coordinator_ca_pem.empty() && !writeString(handle.value, "ca_pem", boot.coordinator_ca_pem)) {
        return false;
    }
    return nvs_commit(handle.value) == ESP_OK;
#endif
}

std::optional<PersonalPendingBootConfig> loadPersonalPendingBootConfigForBoot()
{
    return loadPersonalPendingBootConfigFromNvs();
}

bool trySchedulePersonalPendingBootAfterSntp()
{
    if (notificationUtcMs() == 0) {
        return false;
    }
    auto boot = loadPersonalPendingBootConfigForBoot();
    if (!boot) {
        return false;
    }
    return schedulePersonalPendingBoot(*boot, notificationUtcMs());
}

}  // namespace stackchan::notifications
