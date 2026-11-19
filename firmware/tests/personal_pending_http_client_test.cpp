#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>

#include <esp_transport_ssl.h>
#include <esp_transport_tcp.h>
#include <stackchan/notifications/personal_pending_http_client.h>

using stackchan::notifications::PersonalPendingHttpClient;

struct TestTransport {};

namespace {
TestTransport tcp;
TestTransport tls;
std::string ca;
std::string host;
std::string written;
std::string response;
int connect_result = 0;
int connect_calls = 0;
int ssl_init_calls = 0;
int tcp_init_calls = 0;
int close_calls = 0;
int destroy_calls = 0;
std::size_t read_offset = 0;
bool expect_tls = false;

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

constexpr char kPendingBody[] =
    R"({"items":[{"schema_version":"0.1","notification_id":"ntf_1","delivery_id":"dlv_1",)"
    R"("device_id":"cores3_primary","event_ids":["e1"],"priority":50,"policy_version":"pol_v1",)"
    R"("generation":1,"expires_at":"2026-11-19T12:00:00Z",)"
    R"("presentation_policy":{"ui":true,"audio":false,"motion":true,"tts":false},)"
    R"("presentation_profile":"personal.basic_notice","created_at":"2026-11-19T11:00:00Z"}],"count":1})";
}  // namespace

esp_transport_handle_t esp_transport_tcp_init()
{
    ++tcp_init_calls;
    return &tcp;
}
esp_transport_handle_t esp_transport_ssl_init()
{
    ++ssl_init_calls;
    return &tls;
}
void esp_transport_ssl_set_cert_data(esp_transport_handle_t handle, const char* value, int size)
{
    expect(handle == &tls, "CA on TLS handle");
    ca.assign(value, size);
}
int esp_transport_connect(esp_transport_handle_t handle, const char* name, int port, int timeout)
{
    expect(port == 8443 && timeout == 10000, "port/timeout");
    expect(expect_tls ? handle == &tls : handle == &tcp, "transport kind");
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
    PersonalPendingHttpClient client;
    PersonalPendingHttpClient::Config cleartext{
        "192.168.20.148",
        8443,
        "",
        "device-token-value",
        "cores3_primary",
        4096,
        10000,
        50,
    };

    auto bad = cleartext;
    bad.token = "bad\r\nX";
    expect(!client.fetch(bad) && connect_calls == 0, "header injection rejected");
    bad = cleartext;
    bad.limit = 0;
    expect(!client.fetch(bad) && connect_calls == 0, "limit lower bound");
    bad = cleartext;
    bad.limit = 101;
    expect(!client.fetch(bad) && connect_calls == 0, "limit upper bound");

    expect_tls = false;
    connect_result = -1;
    expect(!client.fetch(cleartext) && tcp_init_calls == 1 && ssl_init_calls == 0, "cleartext connect fail");
    expect(close_calls == 1 && destroy_calls == 1, "release after connect fail");

    connect_result = 0;
    response = "HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n";
    expect(!client.fetch(cleartext), "401 fails closed");
    response = "HTTP/1.1 302 Found\r\nLocation: http://evil/\r\nContent-Length: 0\r\n\r\n";
    expect(!client.fetch(cleartext), "redirect fails closed");

    response = httpOk(kPendingBody);
    const auto ok = client.fetch(cleartext);
    expect(ok.has_value(), "cleartext 200");
    expect(ok->body == kPendingBody, "body forwarded");
    expect(host == "192.168.20.148", "host");
    expect(written.find("GET /v1/devices/cores3_primary/notifications/pending?limit=50 HTTP/1.1\r\n") == 0,
           "pending path");
    expect(written.find("Authorization: Bearer device-token-value\r\n") != std::string::npos, "bearer");
    expect(ssl_init_calls == 0, "cleartext never opens TLS");

    // Pi BaseHTTP 回 HTTP/1.0；須與 1.1 同等接受。
    response = "HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: " +
               std::to_string(std::string_view{kPendingBody}.size()) + "\r\nConnection: close\r\n\r\n" +
               kPendingBody;
    const auto ok10 = client.fetch(cleartext);
    expect(ok10.has_value() && ok10->body == kPendingBody, "HTTP/1.0 200 accepted");

    expect_tls = true;
    PersonalPendingHttpClient::Config https = cleartext;
    https.coordinator_ca_pem = "-----BEGIN CERTIFICATE-----\nmock";
    https.coordinator_host = "coordinator.example";
    response = httpOk(kPendingBody);
    const auto tls_ok = client.fetch(https);
    expect(tls_ok.has_value(), "https 200");
    expect(ca == https.coordinator_ca_pem, "CA set");
    expect(ssl_init_calls >= 1, "TLS used when CA present");
    expect(written.find("Host: coordinator.example\r\n") != std::string::npos, "https host header");
}
