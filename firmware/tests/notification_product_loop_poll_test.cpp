#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
#include <esp_transport_ssl.h>
#include <esp_transport_ws.h>
#include <stackchan/notifications/device_stream_tls_client.h>
#include <stackchan/notifications/fail_closed_guard.h>
#include <stackchan/notifications/notification_presenter.h>
#include <stackchan/notifications/notification_product_loop.h>
#include <stackchan/notifications/presentation_receipt.h>
#include <stackchan/notifications/resource_arbiter.h>
#include <stackchan/notifications/runtime_limits.h>

struct TestTransport {};

namespace {
TestTransport tls, socket;
std::int64_t clock_us = 0;
bool upgrade = false;
}  // namespace

std::int64_t esp_timer_get_time() { return clock_us; }
esp_transport_handle_t esp_transport_ssl_init() { return &tls; }
void esp_transport_ssl_set_cert_data(esp_transport_handle_t, const char*, int) {}
esp_transport_handle_t esp_transport_ws_init(esp_transport_handle_t) { return &socket; }
int esp_transport_ws_set_config(esp_transport_handle_t, const esp_transport_ws_config_t*) { return ESP_OK; }
int esp_transport_connect(esp_transport_handle_t, const char*, int, int) { return upgrade ? 0 : -1; }
int esp_transport_read(esp_transport_handle_t, char*, int, int)
{
    clock_us += 2000;  // Even a nonblocking poll can finish on a later millisecond.
    return 0;
}
int esp_transport_close(esp_transport_handle_t) { return 0; }
int esp_transport_destroy(esp_transport_handle_t) { return 0; }
int esp_transport_ws_get_upgrade_request_status(esp_transport_handle_t) { return upgrade ? 101 : 0; }
int esp_transport_ws_get_read_opcode(esp_transport_handle_t) { return 0; }
int esp_transport_ws_get_read_payload_len(esp_transport_handle_t) { return 0; }
bool esp_transport_ws_get_fin_flag(esp_transport_handle_t) { return true; }

using stackchan::notifications::DeviceStreamTlsClient;
using stackchan::notifications::FailClosedGuard;
using stackchan::notifications::LvglLockHooks;
using stackchan::notifications::LvglLockedUiPort;
using stackchan::notifications::NoticeKind;
using stackchan::notifications::NotificationPresenter;
using stackchan::notifications::NotificationProductLoop;
using stackchan::notifications::NotificationUiPort;
using stackchan::notifications::PresentationReceiptTracker;
using stackchan::notifications::ResourceArbiter;
using stackchan::notifications::kCoreS3MvpRuntimeProfile;
using stackchan::notifications::notificationProductLoopPollClient;
using Outcome = NotificationProductLoop::Outcome;

namespace {
void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

struct FakeUi final : NotificationUiPort {
    std::vector<std::string> ops;
    bool show(NoticeKind, std::string_view text) override
    {
        ops.push_back(std::string("show:") + std::string(text));
        return true;
    }
    void clear() override { ops.push_back("clear"); }
};

void lockFn(void*) {}
void unlockFn(void*) {}

void testPollClientIdleWhenNotStarted()
{
    DeviceStreamTlsClient client{kCoreS3MvpRuntimeProfile.controller, kCoreS3MvpRuntimeProfile.max_frame_age_ms};
    ResourceArbiter arbiter;
    FakeUi inner;
    LvglLockedUiPort ui{inner, LvglLockHooks{lockFn, unlockFn, nullptr}};
    NotificationPresenter presenter{arbiter, ui};
    PresentationReceiptTracker receipts;
    FailClosedGuard guard{client.controller(), presenter, &receipts};
    NotificationProductLoop loop{client.controller(), guard, presenter, &receipts};

    expect(!client.started(), "client not started");
    expect(notificationProductLoopPollClient(loop, client, 10, 1000, 0) == Outcome::Idle,
           "unstarted poll is idle");
    expect(!loop.hasSession(), "no fake session");
    expect(!loop.isPresenting(), "not presenting");
}

void testIoElapsedTimeDoesNotRewindControllerClock()
{
    upgrade = true;
    clock_us = 100000;
    DeviceStreamTlsClient client{kCoreS3MvpRuntimeProfile.controller, kCoreS3MvpRuntimeProfile.max_frame_age_ms};
    ResourceArbiter arbiter;
    FakeUi inner;
    LvglLockedUiPort ui{inner, LvglLockHooks{lockFn, unlockFn, nullptr}};
    NotificationPresenter presenter{arbiter, ui};
    PresentationReceiptTracker receipts;
    FailClosedGuard guard{client.controller(), presenter, &receipts};
    NotificationProductLoop loop{client.controller(), guard, presenter, &receipts};
    const DeviceStreamTlsClient::Config config{
        "coordinator.example", 9445, "-----BEGIN CERTIFICATE-----\nmock", "opaque",
        "device", "v1", 1, UINT64_MAX, 512, 20,
    };
    expect(client.start(config), "verified connection starts recovery");
    expect(notificationProductLoopPollClient(loop, client, 100, 1000, 0) == Outcome::Idle,
           "poll without a heartbeat stays idle");
    expect(client.controller().state(102) == stackchan::notifications::NotificationController::State::Recovering,
           "I/O elapsed time must not look like clock rollback");
    expect(client.poll(0), "transport survives another nonblocking read");
    clock_us = 100000 + kCoreS3MvpRuntimeProfile.controller.heartbeat_timeout_ms * 1000;
    expect(notificationProductLoopPollClient(loop, client, clock_us / 1000, 2000, 0) == Outcome::StreamDead,
           "real heartbeat expiry still closes the connection");
    expect(!client.started() && !loop.hasSession(), "expired session is fully released");
    clock_us = 5000000;
    expect(client.start(config), "connection can restart after heartbeat expiry");
    clock_us = 4999000;
    expect(notificationProductLoopPollClient(loop, client, 4999, 3000, 0) == Outcome::StreamDead,
           "an actual monotonic clock rollback still fails closed");
    expect(!client.started() && !loop.hasSession(), "rollback releases the session");
}
}  // namespace

int main()
{
    testPollClientIdleWhenNotStarted();
    testIoElapsedTimeDoesNotRewindControllerClock();
    return 0;
}
