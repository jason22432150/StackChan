#include "device_stream_tls_client.h"

#include "device_stream_json.h"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <esp_timer.h>
#include <esp_transport_ssl.h>
#include <esp_transport_ws.h>
#include <limits>
#include <new>

namespace stackchan::notifications {
namespace {
using Tick = NotificationController::Tick;

Tick monotonicMs()
{
    return static_cast<Tick>(esp_timer_get_time() / 1000);
}

Tick utcMs()
{
    using namespace std::chrono;
    const auto time = duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count();
    return time > 0 ? static_cast<Tick>(time) : 0;
}

bool printableField(std::string_view text, std::size_t limit)
{
    return !text.empty() && text.size() <= limit && std::all_of(text.begin(), text.end(), [](unsigned char c) {
        return c >= 0x21 && c <= 0x7e;
    });
}

bool validHost(std::string_view host)
{
    return !host.empty() && host.size() <= 253 && std::all_of(host.begin(), host.end(), [](unsigned char c) {
        return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
               c == '.' || c == '-';
    });
}
}  // namespace

DeviceStreamTlsClient::DeviceStreamTlsClient(NotificationController::Limits limits, Tick max_frame_age_ms)
    : _controller(limits), _ingress(_controller, max_frame_age_ms)
{
}

DeviceStreamTlsClient::~DeviceStreamTlsClient()
{
    stop();
}

bool DeviceStreamTlsClient::start(const Config& config)
{
    const auto utc = utcMs();
    constexpr auto max_int = static_cast<std::size_t>(std::numeric_limits<int>::max());
    if (_socket || !validHost(config.coordinator_host) || config.port == 0 ||
        !config.coordinator_ca_pem.starts_with("-----BEGIN CERTIFICATE-----") ||
        config.coordinator_ca_pem.size() >= max_int || config.coordinator_ca_pem.find('\0') != std::string::npos ||
        !printableField(config.device_id, NotificationController::max_id_bytes) ||
        !printableField(config.policy_version, NotificationController::max_id_bytes) ||
        !printableField(config.token, 512) || config.network_timeout_ms <= 0 ||
        utc == 0 || config.policy_expires_utc_ms <= utc ||
        config.max_frame_bytes == 0 || config.max_frame_bytes > max_int ||
        _session == std::numeric_limits<NotificationController::SessionId>::max()) {
        return false;
    }
    auto buffer = std::unique_ptr<char[]>(new (std::nothrow) char[config.max_frame_bytes]);
    if (!buffer) {
        return false;
    }
    ++_session;
    _ca = config.coordinator_ca_pem;
    _tls = esp_transport_ssl_init();
    if (!_tls) {
        stop();
        return false;
    }
    esp_transport_ssl_set_cert_data(_tls, _ca.c_str(), static_cast<int>(_ca.size()));
    _socket = esp_transport_ws_init(_tls);
    if (!_socket) {
        stop();
        return false;
    }
    const auto headers = "Authorization: Bearer " + config.token + "\r\nX-StackChan-Device-Id: " + config.device_id +
                         "\r\nX-StackChan-Policy-Version: " + config.policy_version + "\r\n";
    esp_transport_ws_config_t websocket{};
    websocket.ws_path = "/v1/device-stream";
    websocket.headers = headers.c_str();
    if (esp_transport_ws_set_config(_socket, &websocket) != ESP_OK ||
        esp_transport_connect(_socket, config.coordinator_host.c_str(), config.port, config.network_timeout_ms) != 0 ||
        esp_transport_ws_get_upgrade_request_status(_socket) != 101 ||
        !_ingress.bindVerified(
            {_session, config.device_id, config.policy_version, config.generation, config.policy_expires_utc_ms},
            utcMs(), monotonicMs())) {
        stop();
        return false;
    }
    _receive = std::move(buffer);
    _max_frame_bytes = config.max_frame_bytes;
    _network_timeout_ms = config.network_timeout_ms;
    return true;
}

bool DeviceStreamTlsClient::poll(int read_timeout_ms)
{
    if (!_socket || read_timeout_ms < 0 || read_timeout_ms > _network_timeout_ms) {
        return false;
    }
    if (_controller.state(monotonicMs()) == NotificationController::State::Suspended) {
        stop();
        return false;
    }
    char chunk[256];
    const int count = esp_transport_read(_socket, chunk, sizeof(chunk), read_timeout_ms);
    const auto opcode = esp_transport_ws_get_read_opcode(_socket);
    if (count < 0 || opcode == WS_TRANSPORT_OPCODES_CLOSE ||
        _controller.state(monotonicMs()) == NotificationController::State::Suspended) {
        stop();
        return false;
    }
    if (count == 0) {  // The ESP-IDF transport also handles Ping/Pong here.
        return true;
    }
    const int length = esp_transport_ws_get_read_payload_len(_socket);
    if (opcode != WS_TRANSPORT_OPCODES_TEXT || !esp_transport_ws_get_fin_flag(_socket) || length <= 0) {
        stop();
        return false;
    }
    const auto size = static_cast<std::size_t>(length);
    const auto bytes = static_cast<std::size_t>(count);
    if (_received == 0) {
        _expected = size;
    }
    if (size > _max_frame_bytes || size != _expected || bytes > sizeof(chunk) || bytes > size - _received) {
        stop();
        return false;
    }
    std::memcpy(_receive.get() + _received, chunk, bytes);
    _received += bytes;
    if (_received == _expected) {
        receiveDeviceStreamJson(_ingress, _session, {_receive.get(), _received}, _max_frame_bytes, monotonicMs());
        _received = _expected = 0;
    }
    return true;
}

void DeviceStreamTlsClient::stop()
{
    _ingress.disconnect(_session);
    if (_socket) {
        esp_transport_close(_socket);
        esp_transport_destroy(_socket);
        _socket = nullptr;
    }
    if (_tls) {
        esp_transport_destroy(_tls);
        _tls = nullptr;
    }
    _receive.reset();
    _ca.clear();
    _received = _expected = 0;
}

std::optional<NotificationController::PendingDelivery> DeviceStreamTlsClient::takeNext()
{
    return _controller.takeNext(_session, monotonicMs());
}

}  // namespace stackchan::notifications
