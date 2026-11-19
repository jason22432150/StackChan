#include "notification_product_loop.h"

#include "device_stream_tls_client.h"
#include "personal_pending_ingress.h"
#include "personal_pending_json.h"

#include <algorithm>
#include <esp_timer.h>

namespace stackchan::notifications {

NotificationProductLoop::Outcome notificationProductLoopPollClient(
    NotificationProductLoop& loop, DeviceStreamTlsClient& client, NotificationProductLoop::Tick now,
    NotificationProductLoop::UtcMs reported_at_utc_ms, int read_timeout_ms)
{
    if (!client.started()) {
        // 未佈建／未升級：不開 TLS，亦不假裝有 session。
        return NotificationProductLoop::Outcome::Idle;
    }
    loop.attachSession(client.session());
    const bool alive = client.poll(read_timeout_ms);
    // poll() advances the controller clock while doing I/O. Reusing the
    // caller's earlier timestamp would falsely trigger rollback protection.
    now = std::max(now, static_cast<NotificationProductLoop::Tick>(esp_timer_get_time() / 1000));
    if (!alive) {
        (void)loop.onTransportDisconnected(now, reported_at_utc_ms);
        return NotificationProductLoop::Outcome::StreamDead;
    }
    return loop.tick(now, reported_at_utc_ms);
}

NotificationProductLoop::Outcome notificationProductLoopPollPersonalPending(
    NotificationProductLoop& loop, PersonalPendingIngress& ingress, std::string_view pending_json,
    std::size_t max_json_bytes, NotificationProductLoop::Tick now,
    NotificationProductLoop::UtcMs reported_at_utc_ms)
{
    if (!ingress.bound()) {
        return NotificationProductLoop::Outcome::Idle;
    }
    if (!ingress.pulse(reported_at_utc_ms, now)) {
        (void)loop.onTransportDisconnected(now, reported_at_utc_ms);
        ingress.disconnect(ingress.session());
        return NotificationProductLoop::Outcome::StreamDead;
    }
    if (!pending_json.empty()) {
        (void)applyPersonalPendingJson(ingress, pending_json, max_json_bytes, now);
    }
    loop.attachSession(ingress.session());
    return loop.tick(now, reported_at_utc_ms);
}

}  // namespace stackchan::notifications
