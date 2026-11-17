#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <nvs.h>
#include <stackchan/notifications/notification_credentials.h>
#include <string>
#include <string_view>
#include <thread>

using stackchan::notifications::NotificationCredentialLease;
using stackchan::notifications::NotificationCredentials;
using stackchan::notifications::PendingNotificationCredentials;
using stackchan::notifications::loadNotificationCredentials;

namespace {
const std::map<std::string, std::string> valid_strings{
    {"host", "coordinator.example"},
    {"device_id", "device-a"},
    {"token", "test_token-1"},
    {"ca_pem", "-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----\n"},
};
auto strings = valid_strings;
int open_status = ESP_OK;
int port_status = ESP_OK;
std::uint16_t port = 8443;
int opens = 0;
int closes = 0;
bool handle_open = false;
std::string_view fail_value_read;
std::string_view shrink_value_read;

void expect(bool passed, const char* message)
{
    if (!passed) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

void expectRejected(const char* message)
{
    const int closes_before = closes;
    expect(!loadNotificationCredentials(), message);
    expect(!handle_open && closes == closes_before + (open_status == ESP_OK ? 1 : 0),
           "all opened handles are closed exactly once");
}
}  // namespace

int nvs_open(const char* name, nvs_open_mode_t mode, nvs_handle_t* handle)
{
    ++opens;
    expect(std::string_view(name) == "agent_notify" && mode == NVS_READONLY,
           "read only from the notification namespace");
    if (open_status == ESP_OK) {
        expect(!handle_open, "no previous handle leaked");
        handle_open = true;
        *handle = 42;
    }
    return open_status;
}

void nvs_close(nvs_handle_t handle)
{
    expect(handle == 42 && handle_open, "close the open NVS handle");
    handle_open = false;
    ++closes;
}

int nvs_get_u16(nvs_handle_t handle, const char* key, std::uint16_t* out)
{
    expect(handle == 42 && handle_open && std::string_view(key) == "port", "read port as u16");
    if (port_status == ESP_OK) {
        *out = port;
    }
    return port_status;
}

int nvs_get_str(nvs_handle_t handle, const char* key, char* out, std::size_t* size)
{
    expect(handle == 42 && handle_open, "read via the open NVS handle");
    const auto record = strings.find(key);
    if (record == strings.end()) {
        return ESP_ERR_NVS_NOT_FOUND;
    }
    const auto required = record->second.size() + 1;
    if (out) {
        expect(*size == required, "allocate exactly the bounded string size");
        if (key == fail_value_read) {
            return ESP_ERR_NVS_INVALID_LENGTH;
        }
        std::memcpy(out, record->second.c_str(), required);
    }
    *size = out && key == shrink_value_read ? required - 1 : required;
    return ESP_OK;
}

void testRamCredentialHandoff()
{
    constexpr std::uint64_t now = 1000;
    constexpr std::uint64_t grant_lifetime = 12ULL * 60 * 60 * 1000;
    const NotificationCredentialLease lease{{
        valid_strings.at("host"), 8443, valid_strings.at("ca_pem"),
        valid_strings.at("token"), valid_strings.at("device_id"),
    }, now + grant_lifetime};
    PendingNotificationCredentials pending;
    expect(!pending.take(now), "new RAM store starts empty");
    expect(!pending.stage(lease, 0), "unsynchronized clock cannot stage");
    expect(!pending.stage(lease, lease.expires_at_utc_ms), "expired grant cannot stage");
    expect(!pending.stage(lease, now - 1), "grant beyond pairing lifetime cannot stage");
    expect(pending.stage(lease, now), "valid grant can stage without NVS");

    for (auto field : {&NotificationCredentials::coordinator_host, &NotificationCredentials::device_id,
                       &NotificationCredentials::token, &NotificationCredentials::coordinator_ca_pem}) {
        auto invalid = lease;
        (invalid.credentials.*field).clear();
        expect(!pending.stage(invalid, now), "invalid fields cannot replace a pending grant");
    }
    auto invalid = lease;
    invalid.credentials.port = 0;
    expect(!pending.stage(invalid, now), "invalid port cannot replace a pending grant");
    const auto taken = pending.take(lease.expires_at_utc_ms - 1);
    expect(taken && taken->credentials.token == lease.credentials.token &&
               taken->expires_at_utc_ms == lease.expires_at_utc_ms,
           "handoff retains the original token and expiry");
    expect(!pending.take(lease.expires_at_utc_ms - 1), "grant can be consumed only once");

    expect(pending.stage(lease, now), "grant can be staged again");
    expect(!pending.take(lease.expires_at_utc_ms), "exact expiry clears pending grant");
    expect(!pending.take(now), "clock rollback cannot resurrect an expired grant");
    expect(pending.stage(lease, now), "grant can stage after expiry");
    expect(!pending.take(now - 1) && !pending.take(now), "clock rollback clears pending grant");
    expect(pending.stage(lease, now + 1), "grant can stage at a later time");
    expect(!pending.stage(lease, now) && !pending.take(now + 1), "rollback while staging clears pending grant");
    expect(pending.stage(lease, now), "grant can be staged before cancellation");
    pending.clear();
    expect(!pending.take(now), "clear cancels the handoff");

    expect(pending.stage(lease, now), "grant can be staged for competing consumers");
    bool first = false;
    bool second = false;
    std::thread left([&] { first = pending.take(now).has_value(); });
    std::thread right([&] { second = pending.take(now).has_value(); });
    left.join();
    right.join();
    expect(first != second, "only one concurrent consumer can take the grant");
    expect(opens == 0 && closes == 0, "RAM handoff does not touch NVS");
}

int main()
{
    testRamCredentialHandoff();
#ifndef CONFIG_NVS_ENCRYPTION
    expect(!loadNotificationCredentials() && opens == 0, "unencrypted NVS is never opened");
#else
    const auto credentials = loadNotificationCredentials();
    expect(credentials && credentials->port == 8443 &&
               credentials->coordinator_host == strings.at("host") &&
               credentials->device_id == strings.at("device_id") &&
               credentials->token == strings.at("token") &&
               credentials->coordinator_ca_pem == strings.at("ca_pem"),
           "all credential fields are read");
    expect(opens == 1 && closes == 1 && !handle_open, "success closes NVS");

    open_status = ESP_ERR_NVS_NOT_FOUND;
    expectRejected("missing namespace rejects credentials");
    open_status = ESP_OK;
    port_status = ESP_ERR_NVS_TYPE_MISMATCH;
    expectRejected("wrong port type rejects credentials");
    port_status = ESP_ERR_NVS_NOT_FOUND;
    expectRejected("missing port rejects credentials");
    port_status = ESP_OK;
    port = 0;
    expectRejected("zero port rejects credentials");
    port = 8443;

    for (const auto& [key, value] : valid_strings) {
        strings.erase(key);
        expectRejected("any missing string rejects the entire credential");
        strings[key] = "";
        expectRejected("any empty string rejects the entire credential");
        strings[key] = value;
    }
    for (const auto& [key, value] : std::map<std::string, std::string>{
             {"host", "https://coordinator.example"},
             {"device_id", "../device"},
             {"token", "token\r\ninvalid"},
             {"ca_pem", "-----BEGIN CERTIFICATE-----\ntruncated"},
         }) {
        strings[key] = value;
        expectRejected("invalid credential syntax rejects the entire credential");
        strings[key] = valid_strings.at(key);
    }
    strings["device_id"] = "..";
    expectRejected("device ID cannot be a parent path segment");
    strings["device_id"] = valid_strings.at("device_id");
    strings["token"] = std::string(513, 't');
    expectRejected("oversized token is rejected before reading the value");
    strings["token"] = std::string("test\0suffix", 11);
    expectRejected("embedded NUL rejects the entire credential");
    strings["token"] = valid_strings.at("token");
    fail_value_read = "ca_pem";
    expectRejected("value read failure rejects the entire credential");
    fail_value_read = {};
    shrink_value_read = "ca_pem";
    expectRejected("size changed between reads rejects the entire credential");
#endif
}
