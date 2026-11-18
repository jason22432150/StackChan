#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <esp_timer.h>
#include <esp_transport_ssl.h>
#include <esp_transport_ws.h>
#include <iostream>
#include <string>
#include <stackchan/notifications/avatar_speech_ui.h>
#include <stackchan/notifications/notification_credentials.h>
#include <stackchan/notifications/notification_lvgl_hooks.h>
#include <stackchan/notifications/notification_motion_reactor.h>
#include <stackchan/notifications/notification_pairing_client.h>
#include <stackchan/notifications/notification_product_runtime.h>
#include <stackchan/notifications/notification_utc_clock.h>
#include <stackchan/notifications/stream_bootstrap.h>
#include <stackchan/notifications/stream_session_start.h>

namespace stackchan::notifications {
namespace {
bool hostSpeechShow(void*, NoticeKind, std::string_view)
{
    // host CTest：埠可用即可，避免佇列卡死；不連 Avatar／LVGL。
    return true;
}
void hostSpeechClear(void*) {}
bool hostMotionNudge(void*, const NoticeMotionCommand&) { return true; }
void hostMotionStopHome(void*, const NoticeMotionCommand&) {}
}  // namespace

LvglLockHooks makeHalLvglLockHooks() { return {}; }
AvatarSpeechSink makeDeviceAvatarSpeechSink()
{
    return AvatarSpeechSink{hostSpeechShow, hostSpeechClear, nullptr};
}
NoticeMotionSink makeDeviceNoticeMotionSink()
{
    return NoticeMotionSink{hostMotionNudge, hostMotionStopHome, nullptr};
}
}  // namespace stackchan::notifications

using stackchan::notifications::DeviceStreamTlsClient;
using stackchan::notifications::NotificationPairingEndpoint;
using stackchan::notifications::beginNotificationProductPairing;
using stackchan::notifications::finishNotificationProductPairing;
using stackchan::notifications::NotificationBootstrapResult;
using stackchan::notifications::NotificationUtcClock;
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
int last_connect_port = 0;
NotificationUtcClock notification_clock;
std::uint64_t clock_advance_ms = 0;
std::uint64_t advance_on_http_read_ms = 0;
std::int64_t monotonic_us = 0;
bool disconnect_on_poll = true;
int close_calls = 0;
int destroy_calls = 0;
std::size_t read_offset = 0;
std::size_t read_chunk_limit = 1024;

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

std::string utcAfter(std::uint64_t lifetime_ms)
{
    const auto seconds = static_cast<std::time_t>((nowUtcMs() + lifetime_ms) / 1000);
    char utc[21]{};
    expect(std::strftime(utc, sizeof(utc), "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&seconds)) == 20,
           "UTC test fixture formatted");
    return utc;
}

const NotificationPairingEndpoint pairing_endpoint{
    "paired-coordinator.example", 8443, "-----BEGIN CERTIFICATE-----\nmock\n-----END CERTIFICATE-----\n",
};

constexpr auto pairing_token = "paired-token-for-test";

std::string pairingResponse(std::string_view id, std::uint64_t lifetime_ms,
                            std::string_view token = pairing_token)
{
    return "{\"schema_version\":\"0.1\",\"pairing_id\":\"" + std::string(id) +
           "\",\"subject_id\":\"paired-device\",\"subject_type\":\"device\","
           "\"access_token\":\"" + std::string(token) + "\","
           "\"scopes\":[\"device:policy\",\"device:receipt\",\"device:stream\"],"
           "\"token_expires_at\":\"" + utcAfter(lifetime_ms) + "\"}";
}
}  // namespace

std::uint64_t stackchan::notifications::notificationUtcMs() noexcept
{
    const auto now = notification_clock.utcMs();
    return now == 0 ? 0 : now + clock_advance_ms;
}

std::int64_t esp_timer_get_time() { return monotonic_us; }
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
    expect((port == 8443 || (port == 9443 && handle == &tls)) && timeout == 10000, "configured port and timeout");
    last_connect_port = port;
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
    expect(phase == Phase::Http, "only HTTPS requests write HTTP");
    written.assign(data, size);
    return size;
}
int esp_transport_read(esp_transport_handle_t, char* buffer, int size, int)
{
    if (phase == Phase::Stream) {
        return disconnect_on_poll ? -1 : 0;
    }
    if (read_offset >= http_response.size()) {
        return -1;  // ESP-IDF returns a negative result on TLS closure.
    }
    const auto count = std::min({static_cast<std::size_t>(size), http_response.size() - read_offset, read_chunk_limit});
    std::memcpy(buffer, http_response.data() + read_offset, count);
    read_offset += count;
    if (read_offset == http_response.size()) {
        clock_advance_ms += advance_on_http_read_ms;
        advance_on_http_read_ms = 0;
    }
    return static_cast<int>(count);
}
int esp_transport_close(esp_transport_handle_t) { return ++close_calls, 0; }
int esp_transport_destroy(esp_transport_handle_t) { return ++destroy_calls, 0; }
int esp_transport_ws_get_upgrade_request_status(esp_transport_handle_t) { return http_status; }
int esp_transport_ws_get_read_opcode(esp_transport_handle_t) { return WS_TRANSPORT_OPCODES_TEXT; }
int esp_transport_ws_get_read_payload_len(esp_transport_handle_t) { return 0; }
bool esp_transport_ws_get_fin_flag(esp_transport_handle_t) { return true; }

void testPairingHttps()
{
    using namespace stackchan::notifications;
    NotificationPairingClient pairing;
    using Completion = NotificationPairingClient::Completion;
    auto endpoint = pairing_endpoint;
    endpoint.port = 9443;
    expect(pairing.complete() == Completion::Unavailable && !pairing.start(endpoint, 8443) && connect_calls == 0,
           "a fresh client or unsynchronized clock opens no connection");
    notification_clock.markSynchronized();
    initNotificationProductRuntime();
    constexpr std::string_view id = "pair_0123456789abcdef";
    const std::string claim(43, 'A');
    const auto challenge = [&] {
        return "{\"schema_version\":\"0.1\",\"pairing_id\":\"" + std::string(id) +
               "\",\"subject_type\":\"device\",\"user_code\":\"CODE12\",\"expires_at\":\"" +
               utcAfter(60000) + "\"}";
    };
    const auto claim_header = "X-StackChan-Pairing-Claim: " + claim + "\r\n";
    const auto startResponse = [&](const std::string& headers) {
        http_response = httpOk(challenge());
        http_response.insert(http_response.find("Content-Type:"), headers);
    };

    startResponse(claim_header);
    connect_result = -1;
    expect(!pairing.start(endpoint, 8443) && close_calls == destroy_calls, "TLS connect failure denies pairing");
    connect_result = 0;
    startResponse(claim_header + claim_header);
    expect(!pairing.start(endpoint, 8443), "duplicate claim header is rejected");

    read_chunk_limit = 17;
    startResponse(claim_header);
    expect(pairing.start(endpoint, 8443) == "CODE12", "fragmented start response exposes only human code");
    expect(last_connect_port == 9443 && host == endpoint.coordinator_host && ca == endpoint.coordinator_ca_pem &&
               written.starts_with("POST /v1/pairing/sessions HTTP/1.1\r\n") && written.find(claim) == std::string::npos,
           "start uses trusted pairing endpoint and sends no claim");
    http_response = "HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n";
    expect(pairing.complete() == Completion::Pending, "approval can be checked again before expiry");
    expect(written.starts_with("POST /v1/pairing/sessions/pair_0123456789abcdef/complete HTTP/1.1\r\n") &&
               written.find(claim_header) != std::string::npos,
           "complete presents the claim for the matching pairing");
    http_response = "HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n";
    expect(pairing.complete() == Completion::Unavailable, "denial consumes the local attempt");
    const int denied_calls = connect_calls;
    expect(pairing.complete() == Completion::Unavailable &&
               fetchAndArmNotificationProductRuntime(1) == NotificationBootstrapResult::CredentialsUnavailable &&
               connect_calls == denied_calls, "denial gives no RAM grant and cannot be retried");

    startResponse(claim_header);
    expect(pairing.start(endpoint, 8443) == "CODE12", "fresh pairing starts");
    clock_advance_ms = 61000;
    const int expired_calls = connect_calls;
    expect(pairing.complete() == Completion::Unavailable && connect_calls == expired_calls,
           "expired challenge cannot make a completion request");
    clock_advance_ms = 0;
    startResponse(claim_header);
    expect(pairing.start(endpoint, 8443) == "CODE12", "new challenge can be accepted");
    http_response = httpOk(pairingResponse(id, 10000));
    expect(pairing.complete() == Completion::Delivered, "successful completion stages the grant");
    const int completed_calls = connect_calls;
    expect(pairing.complete() == Completion::Unavailable && connect_calls == completed_calls,
           "successful completion discards its claim");
    http_response = httpOk(R"({"policy_id":"desk","version":"v1","privacy_mode":"private","valid_until":"2099-01-01T00:00:00Z"})");
    expect(fetchAndArmNotificationProductRuntime(1) == NotificationBootstrapResult::Upgraded &&
               last_connect_port == 8443 &&
               ws_headers.find("Authorization: Bearer paired-token-for-test\r\n") != std::string::npos,
           "RAM grant upgrades the stream on its own port");
}

int main(int argc, char** argv)
{
    if (argc == 2 && std::string_view(argv[1]) == "--pairing-https") {
        testPairingHttps();
        return 0;
    }
    if (argc == 2 && std::string_view(argv[1]) == "--after-restart") {
        using namespace stackchan::notifications;
        notification_clock.markSynchronized();
        initNotificationProductRuntime();
        expect(!finishNotificationProductPairing("pair_before_restart", pairingResponse("pair_before_restart", 10000)),
               "fresh process cannot accept a response for a pairing from an earlier boot");
        expect(fetchAndArmNotificationProductRuntime(1) == NotificationBootstrapResult::CredentialsUnavailable &&
                   connect_calls == 0, "fresh process has no saved grant");
        expect(beginNotificationProductPairing("pair_after_restart", utcAfter(60000), pairing_endpoint),
               "a new local pairing can begin after restart");
        expect(!finishNotificationProductPairing("pair_before_restart", pairingResponse("pair_before_restart", 10000)),
               "a prior pairing response cannot complete a different active pairing");
        expect(finishNotificationProductPairing(
                   "pair_after_restart", pairingResponse("pair_after_restart", 10000, "repaired-token-for-test")),
               "newly approved pairing delivers a grant to RAM");
        http_response = httpOk(R"({"policy_id":"desk","version":"v1","privacy_mode":"private","valid_until":"2099-01-01T00:00:00Z"})");
        expect(fetchAndArmNotificationProductRuntime(1) == NotificationBootstrapResult::Upgraded &&
                   connect_calls == 2 &&
                   ws_headers.find("Authorization: Bearer repaired-token-for-test\r\n") != std::string::npos,
               "new grant fetches policy and upgrades after restart");
        return 0;
    }
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
    expect(fetchAndArmNotificationProductRuntime(request.generation) == NotificationBootstrapResult::NotInitialized,
           "explicit fetch requires init");
    initNotificationProductRuntime();
    tickNotificationProductRuntime(0, now_ms, false);
    expect(connect_calls == calls_before_arm && !isNotificationProductStreamArmed(),
           "runtime init leaves stream idle without a connection attempt");
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
    expect(notification_clock.utcMs() == 0, "wall clock alone does not count as SNTP synchronization");
    expect(fetchAndArmNotificationProductRuntime(request.generation) == NotificationBootstrapResult::ClockUnsynchronized,
           "unsynchronized clock blocks bootstrap");
    expect(connect_calls == calls_before_fetch, "unsynchronized clock performs no I/O");
    const auto utc_before_sync = nowUtcMs();
    notification_clock.markSynchronized();
    const auto synchronized_utc = notification_clock.utcMs();
    const auto utc_after_sync = nowUtcMs();
    expect(synchronized_utc >= utc_before_sync && synchronized_utc <= utc_after_sync,
           "after synchronization the clock returns current UTC milliseconds");
    expect(fetchAndArmNotificationProductRuntime(request.generation) == NotificationBootstrapResult::CredentialsUnavailable,
           "missing credentials block bootstrap");
    expect(connect_calls == calls_before_fetch && !isNotificationProductStreamArmed(),
           "missing credentials cause zero connections");

    expect(beginNotificationProductPairing("pair_rejected", utcAfter(60000), pairing_endpoint),
           "locally initiated pairing can await confirmation");
    expect(!finishNotificationProductPairing("pair_rejected", R"({"schema_version":"0.1","error":"forbidden"})"),
           "Coordinator denial does not deliver credentials");
    expect(!finishNotificationProductPairing("pair_rejected", pairingResponse("pair_rejected", 10000)),
           "a denied attempt cannot be reused");
    expect(fetchAndArmNotificationProductRuntime(request.generation) == NotificationBootstrapResult::CredentialsUnavailable &&
               connect_calls == calls_before_fetch, "denied pairing opens no connections");
    expect(beginNotificationProductPairing("pair_wrong_scope", utcAfter(60000), pairing_endpoint),
           "begin a pairing to check scope validation");
    auto wrong_scope = pairingResponse("pair_wrong_scope", 10000);
    wrong_scope.replace(wrong_scope.find("device:stream"), std::strlen("device:stream"), "device:policy");
    expect(!finishNotificationProductPairing("pair_wrong_scope", wrong_scope),
           "duplicate scope cannot replace the required stream scope");
    expect(beginNotificationProductPairing("pair_expired", utcAfter(2000), pairing_endpoint),
           "begin a pairing with a short challenge deadline");
    clock_advance_ms = 3000;
    expect(!finishNotificationProductPairing("pair_expired", pairingResponse("pair_expired", 10000)),
           "expired local challenge cannot deliver credentials");
    clock_advance_ms = 0;

    unsigned pairing_number = 0;
    const auto stage = [&](std::uint64_t lifetime_ms = 10000) {
        const auto id = "pair_" + std::to_string(++pairing_number);
        const auto response = pairingResponse(id, lifetime_ms);
        expect(beginNotificationProductPairing(id, utcAfter(60000), pairing_endpoint) &&
                   finishNotificationProductPairing(id, response),
               "local pairing completion stages a valid RAM grant");
        expect(!finishNotificationProductPairing(id, response), "completed response cannot be replayed");
    };
    phase = Phase::Http;
    stage();
    clock_advance_ms = 20000;
    expect(fetchAndArmNotificationProductRuntime(request.generation) == NotificationBootstrapResult::CredentialsUnavailable &&
               connect_calls == calls_before_fetch, "a staged grant that expires opens no connection");
    clock_advance_ms = 0;
    stage();
    http_response = "HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n";
    expect(fetchAndArmNotificationProductRuntime(request.generation) == NotificationBootstrapResult::PolicyUnavailable,
           "policy denial blocks upgrade");
    expect(connect_calls == calls_before_fetch + 1 && phase == Phase::Http && !isNotificationProductStreamArmed(),
           "policy denial only attempts the policy connection");
    expect(fetchAndArmNotificationProductRuntime(request.generation) == NotificationBootstrapResult::CredentialsUnavailable &&
               connect_calls == calls_before_fetch + 1, "failed bootstrap cannot replay the grant");

    stage();
    http_response = httpOk(R"({"policy_id":"desk","version":"v1","privacy_mode":"private","valid_until":"2099-01-01T00:00:00Z","revoked":true})");
    expect(fetchAndArmNotificationProductRuntime(request.generation) == NotificationBootstrapResult::PolicyUnavailable,
           "revoked lease blocks upgrade");
    expect(connect_calls == calls_before_fetch + 2 && phase == Phase::Http && !isNotificationProductStreamArmed(),
           "revoked lease only attempts the policy connection");

    http_response = httpOk(body);
    stage();
    http_status = 401;
    expect(fetchAndArmNotificationProductRuntime(request.generation) == NotificationBootstrapResult::StreamUpgradeFailed,
           "upgrade denial leaves stream idle");
    expect(connect_calls == calls_before_fetch + 4 && !isNotificationProductStreamArmed(),
           "upgrade denial closes the attempted product stream");

    phase = Phase::Http;
    http_status = 101;
    stage();
    advance_on_http_read_ms = 20000;
    expect(fetchAndArmNotificationProductRuntime(request.generation) == NotificationBootstrapResult::CredentialsUnavailable &&
               connect_calls == calls_before_fetch + 5 && phase == Phase::Http,
           "expiry during policy GET blocks the WebSocket upgrade");
    clock_advance_ms = 0;
    stage(3000);
    expect(fetchAndArmNotificationProductRuntime(request.generation) == NotificationBootstrapResult::Upgraded,
           "valid credentials and policy arm the runtime");
    expect(connect_calls == calls_before_fetch + 7 && isNotificationProductStreamArmed(),
           "successful bootstrap fetches policy and upgrades exactly once");
    expect(written.starts_with("GET /v1/devices/paired-device/policy HTTP/1.1\r\n") &&
               written.find("Authorization: Bearer paired-token-for-test\r\n") != std::string::npos &&
               host == pairing_endpoint.coordinator_host && ca == pairing_endpoint.coordinator_ca_pem,
           "policy GET uses the loaded pairing");
    expect(ws_headers.find("Authorization: Bearer paired-token-for-test\r\n") != std::string::npos &&
               ws_headers.find("X-StackChan-Device-Id: paired-device\r\n") != std::string::npos &&
               ws_headers.find("X-StackChan-Policy-Version: v1\r\n") != std::string::npos,
           "stream upgrade uses the pairing and fetched policy version");

    expect(fetchAndArmNotificationProductRuntime(request.generation) == NotificationBootstrapResult::AlreadyArmed,
           "already armed runtime refuses bootstrap");
    expect(connect_calls == calls_before_fetch + 7, "duplicate bootstrap opens no connections");
    disconnect_on_poll = false;
    tickNotificationProductRuntime(0, nowUtcMs(), false);
    expect(isNotificationProductStreamArmed(), "valid stream can poll before expiry");
    // Cross the grant deadline before the four-second heartbeat deadline.
    monotonic_us = 3500000;
    tickNotificationProductRuntime(3500, nowUtcMs(), false);
    expect(!isNotificationProductStreamArmed(), "grant expiry ends a stream with longer policy validity");
}
