#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <utility>

#include <nvs.h>
#include <stackchan/notifications/personal_pending_boot.h>

using stackchan::notifications::PersonalPendingBootConfig;
using stackchan::notifications::PersonalPendingWorkerRequest;
using stackchan::notifications::buildPersonalPendingWorkerRequest;
using stackchan::notifications::loadPersonalPendingBootConfigFromNvs;
using stackchan::notifications::savePersonalPendingBootConfigToNvs;
using stackchan::notifications::schedulePersonalPendingBoot;
using stackchan::notifications::trySchedulePersonalPendingBootAfterSntp;

namespace {
unsigned scheduled = 0;
std::uint64_t utc_ms = 1'000'000;
PersonalPendingWorkerRequest last_request{};
std::map<std::string, std::string> strings;
std::map<std::string, std::uint16_t> u16s;
std::map<std::string, std::uint32_t> u32s;
int open_status = ESP_OK;
nvs_open_mode_t last_mode = NVS_READONLY;
int opens = 0;
int closes = 0;
int commits = 0;
bool handle_open = false;

void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

PersonalPendingBootConfig sampleBoot()
{
    PersonalPendingBootConfig boot;
    boot.coordinator_host = "192.168.20.148";
    boot.port = 8443;
    boot.device_id = "cores3_primary";
    boot.device_token = "device-token-value-32chars!!!!";
    boot.policy_version = "pol_personal_v1";
    boot.generation = 2;
    boot.session = 3;
    boot.policy_ttl_ms = 86'400'000;
    boot.fetch_interval_ms = 5'000;
    boot.limit = 10;
    return boot;
}
}  // namespace

int nvs_open(const char* name, nvs_open_mode_t mode, nvs_handle_t* handle)
{
    ++opens;
    expect(std::string_view(name) == "personal_pend", "personal_pend namespace");
    last_mode = mode;
    if (open_status == ESP_OK) {
        expect(!handle_open, "no leaked handle");
        handle_open = true;
        *handle = 7;
    }
    return open_status;
}

void nvs_close(nvs_handle_t handle)
{
    expect(handle == 7 && handle_open, "close open handle");
    handle_open = false;
    ++closes;
}

int nvs_get_u16(nvs_handle_t, const char* key, std::uint16_t* out)
{
    const auto it = u16s.find(key);
    if (it == u16s.end()) {
        return ESP_ERR_NVS_NOT_FOUND;
    }
    *out = it->second;
    return ESP_OK;
}

int nvs_get_u32(nvs_handle_t, const char* key, std::uint32_t* out)
{
    const auto it = u32s.find(key);
    if (it == u32s.end()) {
        return ESP_ERR_NVS_NOT_FOUND;
    }
    *out = it->second;
    return ESP_OK;
}

int nvs_get_str(nvs_handle_t, const char* key, char* out, std::size_t* size)
{
    const auto it = strings.find(key);
    if (it == strings.end()) {
        return ESP_ERR_NVS_NOT_FOUND;
    }
    const auto required = it->second.size() + 1;
    if (out) {
        expect(*size == required, "exact string size");
        std::memcpy(out, it->second.c_str(), required);
    }
    *size = required;
    return ESP_OK;
}

int nvs_set_u16(nvs_handle_t, const char* key, std::uint16_t value)
{
    expect(last_mode == NVS_READWRITE, "set requires readwrite");
    u16s[key] = value;
    return ESP_OK;
}

int nvs_set_u32(nvs_handle_t, const char* key, std::uint32_t value)
{
    expect(last_mode == NVS_READWRITE, "set u32 readwrite");
    u32s[key] = value;
    return ESP_OK;
}

int nvs_set_str(nvs_handle_t, const char* key, const char* value)
{
    expect(last_mode == NVS_READWRITE && value != nullptr, "set str");
    strings[key] = value;
    return ESP_OK;
}

int nvs_commit(nvs_handle_t)
{
    ++commits;
    return ESP_OK;
}

namespace stackchan::notifications {
std::uint64_t notificationUtcMs() noexcept { return utc_ms; }
bool requestPersonalPendingNotificationProduct(PersonalPendingWorkerRequest request)
{
    ++scheduled;
    last_request = std::move(request);
    return true;
}
}  // namespace stackchan::notifications

int main()
{
    auto boot = sampleBoot();
    expect(!buildPersonalPendingWorkerRequest(boot, 0), "utc 0 rejected");
    auto request = buildPersonalPendingWorkerRequest(boot, 1'000);
    expect(request.has_value(), "builds request");
    expect(request->policy_expires_utc_ms == 1'000 + 86'400'000, "ttl applied");
    expect(schedulePersonalPendingBoot(boot, 1'000) && scheduled == 1, "schedule");

#if defined(CONFIG_NVS_ENCRYPTION) && CONFIG_NVS_ENCRYPTION
    expect(savePersonalPendingBootConfigToNvs(boot), "save nvs");
    expect(commits == 1 && strings["host"] == "192.168.20.148", "persisted host");
    expect(strings["token"] == boot.device_token, "persisted token");
    expect(u16s["port"] == 8443 && u32s["fetch_ms"] == 5000, "persisted numbers");

    auto loaded = loadPersonalPendingBootConfigFromNvs();
    expect(loaded.has_value(), "load nvs");
    expect(loaded->device_id == "cores3_primary" && loaded->session == 3, "loaded fields");
    expect(loaded->coordinator_ca_pem.empty(), "cleartext ok without ca");

    expect(trySchedulePersonalPendingBootAfterSntp() && scheduled == 2, "sntp hook schedules from nvs");
    expect(last_request.http.device_id == "cores3_primary", "hook uses nvs device");

    open_status = ESP_ERR_NVS_NOT_FOUND;
    expect(!loadPersonalPendingBootConfigFromNvs(), "missing namespace fails closed");
#else
    expect(!savePersonalPendingBootConfigToNvs(boot), "unencrypted save denied");
    expect(!loadPersonalPendingBootConfigFromNvs(), "unencrypted load denied");
    expect(!trySchedulePersonalPendingBootAfterSntp() && scheduled == 1, "no auto schedule without nvs");
#endif
}
