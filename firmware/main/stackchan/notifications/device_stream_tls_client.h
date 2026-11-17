#pragma once

#include "device_stream_ingress.h"

#include <esp_transport.h>
#include <memory>
#include <string>

namespace stackchan::notifications {

class DeviceStreamTlsClient {
public:
    struct Config {
        std::string coordinator_host;
        std::uint16_t port;
        std::string coordinator_ca_pem;
        std::string token;
        std::string device_id;
        std::string policy_version;
        std::uint64_t generation;
        NotificationController::Tick policy_expires_utc_ms;
        std::size_t max_frame_bytes;
        int network_timeout_ms;
    };

    DeviceStreamTlsClient(NotificationController::Limits limits, NotificationController::Tick max_frame_age_ms);
    ~DeviceStreamTlsClient();

    // Public calls belong to the owner task. Provisioning supplies a verified
    // policy snapshot, a trusted CA, and a synchronized system clock.
    bool start(const Config& config);
    bool poll(int read_timeout_ms);
    void stop();
    std::optional<NotificationController::PendingDelivery> takeNext();

    /** 產品主迴圈／FailClosed 共用同一 controller；未 start 時仍可查詢狀態。 */
    NotificationController& controller() { return _controller; }
    const NotificationController& controller() const { return _controller; }
    NotificationController::SessionId session() const { return _session; }
    bool started() const { return _socket != nullptr; }

private:
    NotificationController _controller;
    DeviceStreamIngress _ingress;
    esp_transport_handle_t _tls = nullptr;
    esp_transport_handle_t _socket = nullptr;
    NotificationController::SessionId _session = 0;
    std::string _ca;
    std::unique_ptr<char[]> _receive;
    std::size_t _max_frame_bytes = 0;
    std::size_t _received = 0;
    std::size_t _expected = 0;
    int _network_timeout_ms = 0;
};

}  // namespace stackchan::notifications
