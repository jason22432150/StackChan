#include "notification_product_loop.h"

#include "device_stream_tls_client.h"

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
    if (!client.poll(read_timeout_ms)) {
        (void)loop.onTransportDisconnected(now, reported_at_utc_ms);
        return NotificationProductLoop::Outcome::StreamDead;
    }
    return loop.tick(now, reported_at_utc_ms);
}

}  // namespace stackchan::notifications
