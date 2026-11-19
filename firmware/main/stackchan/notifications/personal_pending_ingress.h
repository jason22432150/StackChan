#pragma once

#include "notification_controller.h"

#include <array>
#include <cstdint>
#include <string_view>

namespace stackchan::notifications {

/**
 * 個人版 HTTP pending → NotificationController 邊界。
 *
 * 呼叫端負責 Device Token 驗證與 JSON 契約；此類只做 session／policy 綁定、
 * UTC→monotonic 期限轉換，以及 enqueue。不開啟 TLS／WebSocket。
 */
class PersonalPendingIngress {
public:
    using Tick = NotificationController::Tick;
    using SessionId = NotificationController::SessionId;

    struct Binding {
        SessionId session;
        std::string_view device_id;
        std::string_view policy_version;
        std::uint64_t generation;
        Tick policy_expires_utc_ms;
    };

    PersonalPendingIngress(NotificationController& controller, Tick max_skew_ms);
    PersonalPendingIngress(const PersonalPendingIngress&) = delete;
    PersonalPendingIngress& operator=(const PersonalPendingIngress&) = delete;

    bool bind(Binding binding, Tick utc_ms, Tick now);
    void disconnect(SessionId session);
    bool bound() const { return _bound; }
    SessionId session() const { return _session; }

    /** 每次成功 HTTP poll 後呼叫，維持 Active（需嚴格遞增的觀測 UTC）。 */
    bool pulse(Tick observed_utc_ms, Tick now);

    /** 將單筆 pending item 轉成 controller enqueue。 */
    bool receiveItem(std::string_view device_id, std::string_view policy_version, std::uint64_t generation,
                     std::string_view delivery_id, Tick expires_utc_ms, Tick now);

private:
    bool clockOk(Tick now) const;

    NotificationController& _controller;
    const Tick _max_skew;
    SessionId _session = 0;
    std::uint64_t _generation = 0;
    std::array<char, NotificationController::max_id_bytes + 1> _device{};
    std::array<char, NotificationController::max_id_bytes + 1> _policy{};
    Tick _bound_at = 0;
    Tick _bound_utc = 0;
    Tick _last_pulse_utc = 0;
    bool _bound = false;
};

}  // namespace stackchan::notifications
