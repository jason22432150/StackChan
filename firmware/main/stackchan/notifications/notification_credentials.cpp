#include "notification_credentials.h"

#include "notification_controller.h"

#include <algorithm>
#include <nvs.h>
#include <sdkconfig.h>
#include <string_view>
#include <utility>

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

bool validCredentials(const NotificationCredentials& credentials)
{
    return credentials.port != 0 &&
           !credentials.coordinator_host.empty() && credentials.coordinator_host.size() <= 253 &&
           std::ranges::all_of(credentials.coordinator_host, [](char c) {
               return alphanumeric(c) || c == '.' || c == '-';
           }) &&
           !credentials.device_id.empty() && credentials.device_id.size() <= NotificationController::max_id_bytes &&
           credentials.device_id != "." && credentials.device_id != ".." &&
           std::ranges::all_of(credentials.device_id, [](char c) {
               return alphanumeric(c) || c == '-' || c == '_' || c == '.' || c == '~';
           }) &&
           !credentials.token.empty() && credentials.token.size() <= 512 &&
           std::ranges::all_of(credentials.token, [](char c) {
               return alphanumeric(c) || c == '-' || c == '_';
           }) &&
           credentials.coordinator_ca_pem.size() <= 3999 &&
           credentials.coordinator_ca_pem.find('\0') == std::string::npos &&
           validPem(credentials.coordinator_ca_pem);
}

}  // namespace

bool PendingNotificationCredentials::stage(NotificationCredentialLease lease, std::uint64_t now_utc_ms)
{
    // The Coordinator's device pairing grant expires after 12 hours.
    constexpr std::uint64_t max_lifetime_ms = 12ULL * 60 * 60 * 1000;
    if (now_utc_ms == 0 || lease.expires_at_utc_ms <= now_utc_ms ||
        lease.expires_at_utc_ms - now_utc_ms > max_lifetime_ms || !validCredentials(lease.credentials)) {
        return false;
    }
    const std::lock_guard lock(_mutex);
    if (_pending && now_utc_ms < _staged_at_utc_ms) {
        _pending.reset();
        return false;
    }
    _pending = std::move(lease);
    _staged_at_utc_ms = now_utc_ms;
    return true;
}

std::optional<NotificationCredentialLease> PendingNotificationCredentials::take(std::uint64_t now_utc_ms)
{
    const std::lock_guard lock(_mutex);
    if (!_pending || now_utc_ms < _staged_at_utc_ms || now_utc_ms >= _pending->expires_at_utc_ms) {
        _pending.reset();
        return std::nullopt;
    }
    return std::exchange(_pending, std::nullopt);
}

void PendingNotificationCredentials::clear()
{
    const std::lock_guard lock(_mutex);
    _pending.reset();
}

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
        !readString(handle.value, "device_id", NotificationController::max_id_bytes, credentials.device_id) ||
        !readString(handle.value, "token", 512, credentials.token) ||
        !readString(handle.value, "ca_pem", 3999, credentials.coordinator_ca_pem) ||
        !validCredentials(credentials)) {
        return std::nullopt;
    }
    return credentials;
}

}  // namespace stackchan::notifications
