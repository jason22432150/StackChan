#include "notification_credentials.h"

#include "notification_controller.h"

#include <algorithm>
#include <nvs.h>
#include <sdkconfig.h>
#include <string_view>

namespace stackchan::notifications {
namespace {

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

bool alphanumeric(char c)
{
    return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z');
}

bool validPem(std::string_view pem)
{
    const auto last = pem.find_last_not_of("\r\n");
    return last != std::string_view::npos && pem.starts_with("-----BEGIN CERTIFICATE-----") &&
           pem.substr(0, last + 1).ends_with("-----END CERTIFICATE-----");
}

}  // namespace

std::optional<NotificationCredentials> loadNotificationCredentials()
{
#ifndef CONFIG_NVS_ENCRYPTION
    return std::nullopt;
#endif
    nvs_handle_t raw_handle;
    if (nvs_open("agent_notify", NVS_READONLY, &raw_handle) != ESP_OK) {
        return std::nullopt;
    }
    const NvsHandle handle{raw_handle};
    NotificationCredentials credentials;
    if (nvs_get_u16(handle.value, "port", &credentials.port) != ESP_OK || credentials.port == 0 ||
        !readString(handle.value, "host", 253, credentials.coordinator_host) ||
        !std::ranges::all_of(credentials.coordinator_host, [](char c) {
            return alphanumeric(c) || c == '.' || c == '-';
        }) ||
        !readString(handle.value, "device_id", NotificationController::max_id_bytes, credentials.device_id) ||
        credentials.device_id == "." || credentials.device_id == ".." ||
        !std::ranges::all_of(credentials.device_id, [](char c) {
            return alphanumeric(c) || c == '-' || c == '_' || c == '.' || c == '~';
        }) ||
        !readString(handle.value, "token", 512, credentials.token) ||
        !std::ranges::all_of(credentials.token, [](char c) {
            return alphanumeric(c) || c == '-' || c == '_';
        }) ||
        !readString(handle.value, "ca_pem", 3999, credentials.coordinator_ca_pem) ||
        !validPem(credentials.coordinator_ca_pem)) {
        return std::nullopt;
    }
    return credentials;
}

}  // namespace stackchan::notifications
