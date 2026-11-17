#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <esp_timer.h>
#include <esp_transport_ssl.h>
#include <esp_transport_ws.h>
#include <iostream>
#include <string>
#include <stackchan/notifications/notification_credentials.h>
#include <stackchan/notifications/notification_lvgl_hooks.h>
#include <stackchan/notifications/notification_product_runtime.h>
#include <stackchan/notifications/stream_bootstrap.h>
#include <stackchan/notifications/stream_session_start.h>

namespace stackchan::notifications {
LvglLockHooks makeHalLvglLockHooks() { return {}; }
}  // namespace stackchan::notifications

using stackchan::notifications::DeviceStreamTlsClient;
using stackchan::notifications::NotificationCredentials;
using stackchan::notifications::PolicyLeaseHttpClient;
using stackchan::notifications::StreamProvisionRequest;
using stackchan::notifications::armProvisionedDeviceStream;
using stackchan::notifications::armProvisionedDeviceStreamLinked;
using stackchan::notifications::fetchAndArmDeviceStream;
using stackchan::notifications::fetchAndArmNotificationProductRuntime;
using stackchan::notifications::fetchAndProvisionDeviceStream;
using stackchan::notifications::kCoreS3MvpRuntimeProfile;
using stackchan::notifications::startProvisionedDeviceStream;
using stackchan::notifications::tickNotificationProductRuntime;

struct TestTransport {};

namespace {
TestTransport tls, socket;
enum class Phase { Http, Stream };
Phase phase = Phase::Http;
std::string ca, host, written, ws_path, ws_headers, http_response;
int connect_result = 0;
int http_status = 101;
int connect_calls = 0;
int credential_reads = 0;
std::optional<NotificationCredentials> stored_credentials;
int close_calls = 0;
int destroy_calls = 0;
std::size_t read_offset = 0;

void expect(bool passed, const char* message)
{
    if (!passed) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

std::string httpOk(std::string_view body)
{
    return "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " +
           std::to_string(body.size()) + "\r\nConnection: close\r\n\r\n" + std::string(body);
}

std::uint64_t nowUtcMs()
{
    using namespace std::chrono;
    return static_cast<std::uint64_t>(
        duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count());
}
}  // namespace

std::optional<NotificationCredentials> stackchan::notifications::loadNotificationCredentials()
{
    ++credential_reads;
    return stored_credentials;
}

std::int64_t esp_timer_get_time() { return 0; }
esp_transport_handle_t esp_transport_ssl_init() { return &tls; }
void esp_transport_ssl_set_cert_data(esp_transport_handle_t handle, const char* value, int size)
{
    expect(handle == &tls, "explicit CA on TLS transport");
    ca.assign(value, size);
}
esp_transport_handle_t esp_transport_ws_init(esp_transport_handle_t parent)
{
    // fetchAndArm：HTTP 結束後才會 ws_init；自動切到 Stream phase。
    if (phase == Phase::Http) {
        phase = Phase::Stream;
    }
    expect(phase == Phase::Stream, "WebSocket only during stream start");
    expect(parent == &tls, "WebSocket parent is TLS");
    return &socket;
}
int esp_transport_ws_set_config(esp_transport_handle_t, const esp_transport_ws_config_t* config)
{
    ws_path = config->ws_path;
    ws_headers = config->headers;
    return ESP_OK;
}
int esp_transport_connect(esp_transport_handle_t handle, const char* name, int port, int timeout)
{
    expect(port == 8443 && timeout == 10000, "MVP network timeout");
    host = name;
    ++connect_calls;
    read_offset = 0;
    if (phase == Phase::Http) {
        expect(handle == &tls, "policy GET uses TLS handle");
    } else {
        expect(handle == &socket, "stream upgrade uses WebSocket handle");
    }
    return connect_result;
}
int esp_transport_write(esp_transport_handle_t, const char* data, int size, int)
{
    expect(phase == Phase::Http, "only policy GET writes HTTP");
    written.assign(data, size);
    return size;
}
int esp_transport_read(esp_transport_handle_t, char* buffer, int size, int)
{
    if (phase == Phase::Stream) {
        return -1;  // Simulate disconnect when the armed runtime polls.
    }
    if (read_offset >= http_response.size()) {
        return 0;
    }
    const auto count = std::min(static_cast<std::size_t>(size), http_response.size() - read_offset);
    std::memcpy(buffer, http_response.data() + read_offset, count);
    read_offset += count;
    return static_cast<int>(count);
}
int esp_transport_close(esp_transport_handle_t) { return ++close_calls, 0; }
int esp_transport_destroy(esp_transport_handle_t) { return ++destroy_calls, 0; }
int esp_transport_ws_get_upgrade_request_status(esp_transport_handle_t) { return http_status; }
int esp_transport_ws_get_read_opcode(esp_transport_handle_t) { return WS_TRANSPORT_OPCODES_TEXT; }
int esp_transport_ws_get_read_payload_len(esp_transport_handle_t) { return 0; }
bool esp_transport_ws_get_fin_flag(esp_transport_handle_t) { return true; }

int main()
{
    PolicyLeaseHttpClient http;
    const auto now_ms = nowUtcMs();
    expect(now_ms > 0, "system clock synchronized for start()");
    StreamProvisionRequest request{
        "coordinator.example",
        8443,
        "-----BEGIN CERTIFICATE-----\nmock",
        "opaque",
        "device-a",
        9,
        {},
        kCoreS3MvpRuntimeProfile,
        now_ms,
    };
    const std::string body =
        R"({"policy_id":"desk","version":"v1","privacy_mode":"private","valid_until":"2099-01-01T00:00:00Z"})";

    phase = Phase::Http;
    connect_result = 0;
    http_response = httpOk(body);
    const auto provision = fetchAndProvisionDeviceStream(http, request);
    expect(provision.has_value(), "fetch and provision succeed");
    expect(written.find("GET /v1/devices/device-a/policy HTTP/1.1\r\n") == 0, "policy fetched first");
    expect(provision->config.policy_version == "v1", "lease version ready for stream");

    DeviceStreamTlsClient client(provision->profile.controller, provision->profile.max_frame_age_ms);
    expect(!startProvisionedDeviceStream(client, {}), "empty provision fails closed");

    phase = Phase::Stream;
    http_status = 401;
    expect(!startProvisionedDeviceStream(client, *provision), "failed upgrade fails closed");

    http_status = 101;
    expect(startProvisionedDeviceStream(client, *provision), "provisioned config starts device stream");
    expect(ws_path == "/v1/device-stream", "stream path fixed");
    expect(ws_headers.find("X-StackChan-Policy-Version: v1\r\n") != std::string::npos,
           "stream uses fetched policy version");
    expect(ws_headers.find("Authorization: Bearer opaque\r\n") != std::string::npos, "bearer reused");
    expect(!client.takeNext(), "upgrade alone cannot enqueue");
    client.stop();
    expect(close_calls > 0 && destroy_calls >= close_calls, "stream stop releases transports");

    // --- P2-04：armProvisionedDeviceStream ---
    expect(!armProvisionedDeviceStream(client, {}), "arm empty provision fails closed");
    expect(!client.started(), "empty arm leaves client idle");

    phase = Phase::Stream;
    http_status = 101;
    expect(armProvisionedDeviceStream(client, *provision), "arm valid provision starts client");
    expect(client.started(), "client.started after arm");
    expect(!armProvisionedDeviceStream(client, *provision), "second arm fails closed");
    client.stop();

    // --- P2-04：fetchAndArmDeviceStream ---
    {
        DeviceStreamTlsClient armed(kCoreS3MvpRuntimeProfile.controller,
                                    kCoreS3MvpRuntimeProfile.max_frame_age_ms);
        phase = Phase::Stream;
        http_status = 101;
        expect(armProvisionedDeviceStream(armed, *provision), "fixture arm");
        expect(!fetchAndArmDeviceStream(http, armed, request), "fetchAndArm rejects already started");
        armed.stop();
    }

    {
        DeviceStreamTlsClient fresh(kCoreS3MvpRuntimeProfile.controller,
                                    kCoreS3MvpRuntimeProfile.max_frame_age_ms);
        phase = Phase::Http;
        connect_result = 0;
        http_response = httpOk(body);
        http_status = 101;
        expect(fetchAndArmDeviceStream(http, fresh, request), "fetchAndArm end-to-end arms stream");
        expect(fresh.started(), "fresh client started after fetchAndArm");
        expect(ws_path == "/v1/device-stream", "fetchAndArm uses device-stream path");
        fresh.stop();
    }

    {
        DeviceStreamTlsClient denied(kCoreS3MvpRuntimeProfile.controller,
                                     kCoreS3MvpRuntimeProfile.max_frame_age_ms);
        phase = Phase::Http;
        connect_result = 0;
        http_response = httpOk(body);
        http_status = 401;
        expect(!fetchAndArmDeviceStream(http, denied, request), "fetchAndArm upgrade 401 fails closed");
        expect(!denied.started(), "denied client not left started");
    }

    expect(armProvisionedDeviceStreamLinked(), "arm link retain probe");

    using stackchan::notifications::armNotificationProductRuntime;
    using stackchan::notifications::initNotificationProductRuntime;
    using stackchan::notifications::isNotificationProductStreamArmed;
    const int calls_before_arm = connect_calls;
    expect(!armNotificationProductRuntime(*provision), "runtime rejects arm before init");
    expect(!fetchAndArmNotificationProductRuntime(request.generation, now_ms), "explicit fetch requires init");
    initNotificationProductRuntime();
    tickNotificationProductRuntime(0, now_ms, false);
    expect(connect_calls == calls_before_arm && !isNotificationProductStreamArmed(),
           "runtime init leaves stream idle without a connection attempt");
    expect(credential_reads == 0, "uninitialized call, init and idle tick never load credentials");
    phase = Phase::Stream;
    http_status = 101;

    // Each mismatch is within generic limits and tested independently.
    const auto reject = [&](const auto& profile) {
        auto candidate = *provision;
        candidate.profile = profile;
        candidate.config.max_frame_bytes = profile.max_frame_bytes;
        candidate.config.network_timeout_ms = profile.network_timeout_ms;
        expect(!armNotificationProductRuntime(candidate), "runtime rejects a non-MVP profile");
        expect(connect_calls == calls_before_arm && !isNotificationProductStreamArmed(),
               "profile mismatch leaves runtime idle without a connection attempt");
    };
    auto profile = request.profile;
    profile.controller.capacity--;
    reject(profile);
    profile = request.profile;
    profile.controller.heartbeat_timeout_ms++;
    reject(profile);
    profile = request.profile;
    profile.controller.stability_ms--;
    reject(profile);
    profile = request.profile;
    profile.max_frame_age_ms++;
    reject(profile);
    profile = request.profile;
    profile.max_frame_bytes++;
    reject(profile);
    profile = request.profile;
    profile.network_timeout_ms++;
    reject(profile);

    expect(armNotificationProductRuntime(*provision), "runtime arms with the MVP profile");
    expect(isNotificationProductStreamArmed() && connect_calls == calls_before_arm + 1,
           "matching profile upgraded exactly once");

    tickNotificationProductRuntime(0, now_ms, false);
    expect(!isNotificationProductStreamArmed(), "transport failure releases the existing stream");
    const int calls_before_fetch = connect_calls;
    expect(!fetchAndArmNotificationProductRuntime(request.generation, 0), "missing UTC blocks bootstrap");
    expect(credential_reads == 0 && connect_calls == calls_before_fetch, "missing UTC performs no I/O");
    expect(!fetchAndArmNotificationProductRuntime(request.generation, now_ms), "missing credentials block bootstrap");
    expect(credential_reads == 1 && connect_calls == calls_before_fetch && !isNotificationProductStreamArmed(),
           "missing credentials cause zero connections");

    stored_credentials = NotificationCredentials{
        "paired-coordinator.example", request.port, request.coordinator_ca_pem, "paired-token", "paired-device",
    };
    phase = Phase::Http;
    http_response = "HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n";
    expect(!fetchAndArmNotificationProductRuntime(request.generation, now_ms), "policy denial blocks upgrade");
    expect(connect_calls == calls_before_fetch + 1 && phase == Phase::Http && !isNotificationProductStreamArmed(),
           "policy denial only attempts the policy connection");

    http_response = httpOk(R"({"policy_id":"desk","version":"v1","privacy_mode":"private","valid_until":"2099-01-01T00:00:00Z","revoked":true})");
    expect(!fetchAndArmNotificationProductRuntime(request.generation, now_ms), "revoked lease blocks upgrade");
    expect(connect_calls == calls_before_fetch + 2 && phase == Phase::Http && !isNotificationProductStreamArmed(),
           "revoked lease only attempts the policy connection");

    http_response = httpOk(body);
    http_status = 401;
    expect(!fetchAndArmNotificationProductRuntime(request.generation, now_ms), "upgrade denial leaves stream idle");
    expect(connect_calls == calls_before_fetch + 4 && !isNotificationProductStreamArmed(),
           "upgrade denial closes the attempted product stream");

    phase = Phase::Http;
    http_status = 101;
    expect(fetchAndArmNotificationProductRuntime(request.generation, now_ms), "valid credentials and policy arm the runtime");
    expect(connect_calls == calls_before_fetch + 6 && isNotificationProductStreamArmed(),
           "successful bootstrap fetches policy and upgrades exactly once");
    expect(written.starts_with("GET /v1/devices/paired-device/policy HTTP/1.1\r\n") &&
               written.find("Authorization: Bearer paired-token\r\n") != std::string::npos &&
               host == stored_credentials->coordinator_host && ca == stored_credentials->coordinator_ca_pem,
           "policy GET uses the loaded pairing");
    expect(ws_headers.find("Authorization: Bearer paired-token\r\n") != std::string::npos &&
               ws_headers.find("X-StackChan-Device-Id: paired-device\r\n") != std::string::npos &&
               ws_headers.find("X-StackChan-Policy-Version: v1\r\n") != std::string::npos,
           "stream upgrade uses the pairing and fetched policy version");

    const int reads_after_arm = credential_reads;
    expect(!fetchAndArmNotificationProductRuntime(request.generation, now_ms), "already armed runtime refuses bootstrap");
    expect(credential_reads == reads_after_arm && connect_calls == calls_before_fetch + 6,
           "duplicate bootstrap reads no credentials and opens no connections");
    tickNotificationProductRuntime(0, now_ms, false);
}
