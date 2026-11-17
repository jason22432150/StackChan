#include <cstdlib>
#include <cstring>
#include <esp_transport_ssl.h>
#include <iostream>
#include <limits>
#include <string>
#include <stackchan/notifications/policy_lease.h>
#include <stackchan/notifications/policy_lease_http_client.h>

using stackchan::notifications::PolicyLeaseHttpClient;
using stackchan::notifications::applyPolicyLeaseToStreamFields;

struct TestTransport {};

namespace {
TestTransport tls;
std::string ca, host, written;
std::string response;
int connect_result = 0;
int connect_calls = 0;
int close_calls = 0;
int destroy_calls = 0;
std::size_t read_offset = 0;
// 2026-11-16T12:00:00Z
constexpr auto now_ms = 1'794'830'400'000ULL;

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
void esp_transport_ssl_set_cert_data(esp_transport_handle_t handle, const char* value, int size)
{
    expect(handle == &tls, "explicit CA belongs to TLS transport");
    ca.assign(value, size);
}
int esp_transport_connect(esp_transport_handle_t, const char* name, int port, int timeout)
{
    expect(port == 8443 && timeout == 10000, "configured port and timeout");
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
    PolicyLeaseHttpClient client;
    const PolicyLeaseHttpClient::Config config{
        "coordinator.example",
        8443,
        "-----BEGIN CERTIFICATE-----\nmock",
        "opaque",
        "device-a",
        1024,
        10000,
    };
    const std::string body =
        R"({"policy_id":"desk","version":"v1","privacy_mode":"private","valid_until":"2026-11-17T12:00:00Z"})";

    auto invalid = config;
    invalid.token = "bad\r\nInjected";
    expect(!client.fetch(invalid, now_ms) && connect_calls == 0, "header injection rejected before connect");
    invalid = config;
    invalid.coordinator_ca_pem.clear();
    expect(!client.fetch(invalid, now_ms) && connect_calls == 0, "missing CA fails closed");

    connect_result = -1;
    expect(!client.fetch(config, now_ms) && connect_calls == 1, "TLS connect failure denies lease");
    expect(close_calls == 1 && destroy_calls == 1, "failed connect still releases transport");

    connect_result = 0;
    response = "HTTP/1.1 302 Found\r\nLocation: https://evil/\r\nContent-Length: 0\r\n\r\n";
    expect(!client.fetch(config, now_ms), "redirect fails closed");
    response = "HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n";
    expect(!client.fetch(config, now_ms), "unauthorized fails closed");
    response =
        "HTTP/1.1 200 OK\r\nLocation: https://evil/\r\nContent-Length: " + std::to_string(body.size()) +
        "\r\n\r\n" + body;
    expect(!client.fetch(config, now_ms), "Location header on 200 fails closed");

    response = httpOk(body);
    const auto lease = client.fetch(config, now_ms);
    expect(lease.has_value(), "200 Policy JSON becomes a binding");
    expect(ca == config.coordinator_ca_pem && host == config.coordinator_host, "CA and host forwarded");
    expect(written.find("GET /v1/devices/device-a/policy HTTP/1.1\r\n") == 0, "fixed policy path");
    expect(written.find("Authorization: Bearer opaque\r\n") != std::string::npos, "bearer token sent");
    expect(std::string_view(lease->version.data()) == "v1", "version bound from body");
    expect(lease->expires_utc_ms == 1'794'916'800'000ULL, "expires_utc_ms from valid_until");

    const auto length = std::to_string(body.size());
    auto fetchWithHeaders = [&](std::string_view status, const std::string& headers) {
        response = std::string(status) + "\r\n" + headers + "\r\n\r\n" + body;
        return client.fetch(config, now_ms);
    };
    expect(fetchWithHeaders("HTTP/1.1 200 OK", "cOnTeNt-LeNgTh:\t" + length + " \t").has_value(),
           "mixed-case field name and HTTP optional whitespace are accepted");
    expect(!fetchWithHeaders("HTTP/1.1 200OK", "Content-Length: " + length),
           "malformed status line is rejected");
    expect(!fetchWithHeaders("HTTP/1.1 200 OK", "Content-Type: application/json"),
           "missing length is rejected");
    for (const auto& headers : {
             "Content-Length: " + length + "\r\ncOnTeNt-LeNgTh: " + length,
             "Content-Length: " + length + "\r\nContent-Length: 0",
             "Content-Length: " + length + "\r\ntRaNsFeR-EnCoDiNg: chunked",
             "Content-Length: " + length + "\r\n transfer-encoding: chunked",
             "Content-Length: " + length + "\r\nTransfer-Encoding : chunked",
             "Content-Length: " + length + "\r\nX-Test: value\nTransfer-Encoding: chunked",
             "Content-Length: " + std::to_string(body.size() + 1),
             "Content-Length: " + std::to_string(std::numeric_limits<std::size_t>::max()) + length,
         }) {
        expect(!fetchWithHeaders("HTTP/1.1 200 OK", headers), "invalid response framing is rejected");
    }

    std::string policy_version;
    std::uint64_t expires = 0;
    expect(applyPolicyLeaseToStreamFields(policy_version, expires, *lease, now_ms),
           "lease applies to stream fields");
    expect(policy_version == "v1" && expires == lease->expires_utc_ms, "stream fields filled");
    expect(!applyPolicyLeaseToStreamFields(policy_version, expires, *lease, lease->expires_utc_ms),
           "expired lease cannot fill stream fields");

    response = httpOk(R"({"policy_id":"desk","version":"v1","privacy_mode":"private","valid_until":"2026-11-16T11:00:00Z"})");
    expect(!client.fetch(config, now_ms), "expired policy body rejected");
    expect(close_calls == destroy_calls, "each TLS transport closed and destroyed once");
}
