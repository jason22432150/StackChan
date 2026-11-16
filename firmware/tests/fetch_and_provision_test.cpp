#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <esp_transport_ssl.h>
#include <iostream>
#include <string>
#include <stackchan/notifications/stream_bootstrap.h>

using stackchan::notifications::PolicyLeaseHttpClient;
using stackchan::notifications::StreamProvisionRequest;
using stackchan::notifications::fetchAndProvisionDeviceStream;
using stackchan::notifications::kCoreS3MvpRuntimeProfile;

struct TestTransport {};

namespace {
TestTransport tls;
std::string ca, host, written, response;
int connect_result = 0;
int connect_calls = 0;
int close_calls = 0;
int destroy_calls = 0;
std::size_t read_offset = 0;
constexpr auto now_ms = 1'794'830'400'000ULL;
constexpr auto expires_ms = 1'794'916'800'000ULL;

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
}  // namespace

esp_transport_handle_t esp_transport_ssl_init() { return &tls; }
void esp_transport_ssl_set_cert_data(esp_transport_handle_t, const char* value, int size)
{
    ca.assign(value, size);
}
int esp_transport_connect(esp_transport_handle_t, const char* name, int port, int timeout)
{
    expect(port == 8443 && timeout == 10000, "MVP network timeout used for policy GET");
    host = name;
    ++connect_calls;
    read_offset = 0;
    return connect_result;
}
int esp_transport_write(esp_transport_handle_t, const char* data, int size, int)
{
    written.assign(data, size);
    return size;
}
int esp_transport_read(esp_transport_handle_t, char* buffer, int size, int)
{
    if (read_offset >= response.size()) {
        return 0;
    }
    const auto count = std::min(static_cast<std::size_t>(size), response.size() - read_offset);
    std::memcpy(buffer, response.data() + read_offset, count);
    read_offset += count;
    return static_cast<int>(count);
}
int esp_transport_close(esp_transport_handle_t) { return ++close_calls, 0; }
int esp_transport_destroy(esp_transport_handle_t) { return ++destroy_calls, 0; }

int main()
{
    PolicyLeaseHttpClient http;
    StreamProvisionRequest request{
        "coordinator.example",
        8443,
        "-----BEGIN CERTIFICATE-----\nmock",
        "opaque",
        "device-a",
        3,
        {},
        kCoreS3MvpRuntimeProfile,
        now_ms,
    };
    const std::string body =
        R"({"policy_id":"desk","version":"v1","privacy_mode":"private","valid_until":"2026-11-17T12:00:00Z"})";

    connect_result = -1;
    expect(!fetchAndProvisionDeviceStream(http, request) && connect_calls == 1,
           "TLS failure blocks provision");
    expect(close_calls == destroy_calls, "failed fetch releases transport");

    connect_result = 0;
    response = "HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n";
    expect(!fetchAndProvisionDeviceStream(http, request), "non-200 policy denies stream config");

    response = httpOk(body);
    const auto provision = fetchAndProvisionDeviceStream(http, request);
    expect(provision.has_value(), "policy GET plus MVP profile provisions stream config");
    expect(written.find("GET /v1/devices/device-a/policy HTTP/1.1\r\n") == 0, "policy path fetched");
    expect(ca == request.coordinator_ca_pem && host == request.coordinator_host, "CA and host reused");
    expect(provision->config.policy_version == "v1", "lease version applied");
    expect(provision->config.policy_expires_utc_ms == expires_ms, "lease expiry applied");
    expect(provision->config.max_frame_bytes == 1024, "MVP frame ceiling applied");
    expect(provision->config.network_timeout_ms == 10000, "MVP network timeout applied");
    expect(provision->config.generation == 3, "generation preserved");
    expect(provision->profile.controller.capacity == 4, "MVP controller limits retained");
    expect(close_calls == destroy_calls, "successful fetch releases transport");
}
