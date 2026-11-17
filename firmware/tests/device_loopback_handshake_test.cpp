#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <stackchan/notifications/device_loopback_handshake.h>
#include <stackchan/notifications/device_stream_json.h>

using stackchan::notifications::DeviceLoopbackHandshakeRequest;
using stackchan::notifications::DeviceStreamIngress;
using stackchan::notifications::NotificationController;
using stackchan::notifications::StreamProvisionRequest;
using stackchan::notifications::completeDeviceLoopbackHandshake;
using stackchan::notifications::deviceLoopbackHandshakeLinked;
using stackchan::notifications::kCoreS3MvpRuntimeProfile;
using stackchan::notifications::receiveDeviceStreamJson;
using State = NotificationController::State;

namespace {
void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

// 與 Coordinator loopback fixture 相同的 OpenAPI Policy 快照（valid_until 遠未來）。
constexpr auto kLoopbackPolicyJson =
    R"({"policy_id":"desk","version":"v1","privacy_mode":"private","valid_until":"2099-01-01T00:00:00Z"})";
// 2026-11-16T12:00:00.000Z — 僅用於 parsePolicyLeaseJson／lease 有效性（與 policy_lease_test 對齊）。
constexpr auto kNowUtcMs = 1'794'830'400'000ULL;
// Ingress 時鐘錨點採小整數 UTC，以便與既有 heartbeat sent_at（1970 epoch ms）對齊。
constexpr auto kTrustedPeerUtcMs = 1'000ULL;
constexpr std::size_t kPolicyLimit = 256;
constexpr std::size_t kFrameLimit = 1024;

StreamProvisionRequest baseProvision()
{
    return StreamProvisionRequest{
        "127.0.0.1",
        8443,
        "-----BEGIN CERTIFICATE-----\nloopback-ca\n-----END CERTIFICATE-----\n",
        "device-token",
        "device-a",
        1,
        {},
        kCoreS3MvpRuntimeProfile,
        kNowUtcMs,
    };
}

void testHappyPathActivatesAndQueuesIntent()
{
    // Controller 使用短 stability，以便本測試在單一心跳後進入 Active；
    // provision 仍走 kCoreS3MvpRuntimeProfile（與 loopback／裝置 Config 對齊）。
    NotificationController controller({4, 4000, 5});
    DeviceStreamIngress ingress(controller, kCoreS3MvpRuntimeProfile.max_frame_age_ms);

    DeviceLoopbackHandshakeRequest request{};
    request.policy_json = kLoopbackPolicyJson;
    request.max_policy_bytes = kPolicyLimit;
    request.provision = baseProvision();
    request.session = 1;
    request.trusted_peer_utc_ms = kTrustedPeerUtcMs;
    request.now_ms = 0;

    const auto handshake = completeDeviceLoopbackHandshake(ingress, request);
    expect(handshake.has_value(), "loopback policy→provision→bind succeeds");
    expect(std::string_view(handshake->lease.version.data()) == "v1", "lease version from loopback");
    expect(handshake->provision.config.generation == 1, "generation retained for stream headers");
    expect(handshake->provision.config.policy_version == "v1", "stream Config uses lease version");
    expect(handshake->provision.config.device_id == "device-a", "device scope for stream headers");
    expect(controller.state(0) == State::Recovering, "bound but inactive until heartbeat");

    // 與 loopback device-stream envelope 契約對齊的 heartbeat／intent（epoch 毫秒時間戳）。
    const std::string heartbeat =
        R"({"schema_version":"0.1","message_id":"h1","device_id":"device-a","policy_version":"v1","generation":1,"direction":"coordinator_to_device","type":"heartbeat","sent_at":"1970-01-01T00:00:01.005Z"})";
    const std::string intent =
        R"({"schema_version":"0.1","message_id":"i1","device_id":"device-a","policy_version":"v1","generation":1,"direction":"coordinator_to_device","type":"notification.intent","sent_at":"1970-01-01T00:00:01.006Z","delivery_id":"d1","payload":{"schema_version":"0.1","notification_id":"n1","delivery_id":"d1","device_id":"device-a","event_ids":["e1"],"priority":10,"policy_version":"v1","generation":1,"expires_at":"1970-01-01T00:00:01.500Z","presentation_policy":{"ui":true,"audio":false,"motion":false,"tts":false}}})";

    expect(receiveDeviceStreamJson(ingress, 1, heartbeat, kFrameLimit, 5), "post-handshake heartbeat activates");
    expect(controller.state(5) == State::Active, "device session Active after loopback heartbeat");
    expect(receiveDeviceStreamJson(ingress, 1, intent, kFrameLimit, 6), "intent accepted after handshake");
    const auto delivery = controller.takeNext(1, 6);
    expect(delivery && std::string_view(delivery->id.data()) == "d1", "delivery queued from loopback-shaped intent");
}

void testFailClosedRejectsBadPolicyAndMissingTrust()
{
    NotificationController controller({4, 4000, 5});
    DeviceStreamIngress ingress(controller, kCoreS3MvpRuntimeProfile.max_frame_age_ms);

    DeviceLoopbackHandshakeRequest missing_peer = {};
    missing_peer.policy_json = kLoopbackPolicyJson;
    missing_peer.max_policy_bytes = kPolicyLimit;
    missing_peer.provision = baseProvision();
    missing_peer.session = 1;
    missing_peer.trusted_peer_utc_ms = 0;
    missing_peer.now_ms = 0;
    expect(!completeDeviceLoopbackHandshake(ingress, missing_peer), "missing trusted peer UTC fails closed");

    DeviceLoopbackHandshakeRequest revoked = {};
    revoked.policy_json =
        R"({"policy_id":"desk","version":"v1","privacy_mode":"private","valid_until":"2099-01-01T00:00:00Z","revoked":true})";
    revoked.max_policy_bytes = kPolicyLimit;
    revoked.provision = baseProvision();
    revoked.session = 2;
    revoked.trusted_peer_utc_ms = kTrustedPeerUtcMs;
    revoked.now_ms = 0;
    expect(!completeDeviceLoopbackHandshake(ingress, revoked), "revoked policy fails closed");
    expect(controller.state(0) == State::Suspended, "failed handshake leaves controller Suspended");
}

void testWrongPolicyVersionCannotActivate()
{
    NotificationController controller({4, 4000, 5});
    DeviceStreamIngress ingress(controller, kCoreS3MvpRuntimeProfile.max_frame_age_ms);

    DeviceLoopbackHandshakeRequest request{};
    request.policy_json = kLoopbackPolicyJson;
    request.max_policy_bytes = kPolicyLimit;
    request.provision = baseProvision();
    request.session = 3;
    request.trusted_peer_utc_ms = kTrustedPeerUtcMs;
    request.now_ms = 0;
    expect(completeDeviceLoopbackHandshake(ingress, request).has_value(), "handshake binds v1");

    const std::string wrong =
        R"({"schema_version":"0.1","message_id":"h","device_id":"device-a","policy_version":"wrong","generation":1,"direction":"coordinator_to_device","type":"heartbeat","sent_at":"1970-01-01T00:00:01.005Z"})";
    expect(!receiveDeviceStreamJson(ingress, 3, wrong, kFrameLimit, 5), "mismatched policy version rejected");
    expect(controller.state(5) == State::Recovering, "wrong stream version cannot activate");
}
}  // namespace

int main()
{
    expect(deviceLoopbackHandshakeLinked(), "link probe available");
    testHappyPathActivatesAndQueuesIntent();
    testFailClosedRejectsBadPolicyAndMissingTrust();
    testWrongPolicyVersionCannotActivate();
}
