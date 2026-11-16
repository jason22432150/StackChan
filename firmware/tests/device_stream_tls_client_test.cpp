#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <esp_transport_ssl.h>
#include <esp_transport_ws.h>
#include <iostream>
#include <stackchan/notifications/device_stream_tls_client.h>

using stackchan::notifications::DeviceStreamTlsClient;

struct TestTransport {};

namespace {
TestTransport tls, socket;
std::int64_t clock_us = 0;
int connect_result = 0;
int http_status = 101;
int connect_calls = 0;
int close_calls = 0;
int destroy_calls = 0;
int frame_opcode = WS_TRANSPORT_OPCODES_TEXT;
int frame_length = 0;
int chunk_length = 0;
bool frame_fin = true;
std::string ca, host, path, headers;

void expect(bool passed, const char* message)
{
    if (!passed) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}
}  // namespace

std::int64_t esp_timer_get_time() { return clock_us; }
esp_transport_handle_t esp_transport_ssl_init() { return &tls; }
void esp_transport_ssl_set_cert_data(esp_transport_handle_t handle, const char* value, int size)
{
    expect(handle == &tls, "explicit CA belongs to TLS transport");
    ca.assign(value, size);
}
esp_transport_handle_t esp_transport_ws_init(esp_transport_handle_t parent)
{
    expect(parent == &tls, "WebSocket cannot use a plaintext parent");
    return &socket;
}
int esp_transport_ws_set_config(esp_transport_handle_t, const esp_transport_ws_config_t* config)
{
    headers = config->headers;
    path = config->ws_path;
    return ESP_OK;
}
int esp_transport_connect(esp_transport_handle_t, const char* name, int port, int timeout)
{
    expect(port == 8443 && timeout == 20, "configured port and timeout are passed through");
    host = name;
    ++connect_calls;
    return connect_result;
}
int esp_transport_read(esp_transport_handle_t, char* buffer, int size, int)
{
    if (chunk_length > 0) {
        expect(chunk_length <= size, "test input fits read buffer");
        std::memset(buffer, ' ', chunk_length);
    }
    return chunk_length;
}
int esp_transport_close(esp_transport_handle_t) { return ++close_calls, 0; }
int esp_transport_destroy(esp_transport_handle_t) { return ++destroy_calls, 0; }
int esp_transport_ws_get_upgrade_request_status(esp_transport_handle_t) { return http_status; }
int esp_transport_ws_get_read_opcode(esp_transport_handle_t) { return frame_opcode; }
int esp_transport_ws_get_read_payload_len(esp_transport_handle_t) { return frame_length; }
bool esp_transport_ws_get_fin_flag(esp_transport_handle_t) { return frame_fin; }

int main()
{
    DeviceStreamTlsClient client({2, 100, 1}, 10);
    const DeviceStreamTlsClient::Config config{
        "coordinator.example", 8443, "-----BEGIN CERTIFICATE-----\nmock", "opaque",
        "device", "v1", 1, UINT64_MAX, 512, 20,
    };

    auto invalid = config;
    invalid.token = "bad\r\nInjected";
    expect(!client.start(invalid) && connect_calls == 0, "invalid header is rejected before connecting");
    invalid = config;
    invalid.coordinator_ca_pem.clear();
    expect(!client.start(invalid) && connect_calls == 0, "missing CA fails closed");
    invalid = config;
    invalid.coordinator_host = "ws://coordinator.example";
    expect(!client.start(invalid) && connect_calls == 0, "only a hostname or IPv4 component is accepted");

    connect_result = http_status = 302;
    expect(!client.start(config) && connect_calls == 1 && destroy_calls == 2,
           "redirect closes transport without following it");
    connect_result = 0;
    http_status = 401;
    expect(!client.start(config) && connect_calls == 2, "non-upgrade response fails even with a zero result");
    connect_result = -1;
    expect(!client.start(config) && connect_calls == 3 && !client.takeNext(), "TLS failure denies notifications");

    connect_result = 0;
    http_status = 101;
    expect(client.start(config), "verified upgrade starts recovery");
    expect(ca == config.coordinator_ca_pem && host == config.coordinator_host && path == "/v1/device-stream",
           "saved CA, host and fixed path are forwarded");
    expect(headers == "Authorization: Bearer opaque\r\nX-StackChan-Device-Id: device\r\n"
                      "X-StackChan-Policy-Version: v1\r\n", "Coordinator scope headers");
    expect(!client.takeNext(), "an upgrade alone cannot dispatch");
    frame_length = 400;
    chunk_length = 200;
    expect(client.poll(1) && client.poll(1) && !client.takeNext(),
           "read chunks are reassembled; invalid JSON cannot enter the queue");
    frame_length = 513;
    expect(!client.poll(1) && !client.takeNext(), "oversized frame closes session");

    expect(client.start(config), "new connection can start after an error");
    frame_fin = false;
    frame_length = 400;
    expect(!client.poll(1), "unsupported fragmented text frame closes session");
    expect(client.start(config), "new connection after invalid frame");
    frame_opcode = WS_TRANSPORT_OPCODES_CLOSE;
    chunk_length = 0;
    expect(!client.poll(1) && !client.takeNext(), "close frame revokes session even if empty");
    expect(client.start(config), "new connection after close");
    clock_us = 100'000;
    expect(!client.poll(1) && !client.takeNext(), "heartbeat deadline closes silent link");
    expect(close_calls * 2 == destroy_calls, "each socket and TLS parent released once");
}
