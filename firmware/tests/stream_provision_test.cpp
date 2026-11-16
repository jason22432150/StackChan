#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <stackchan/notifications/stream_provision.h>

using stackchan::notifications::NotificationController;
using stackchan::notifications::PolicyLeaseBinding;
using stackchan::notifications::StreamProvisionRequest;
using stackchan::notifications::kCoreS3MvpRuntimeProfile;
using stackchan::notifications::provisionDeviceStream;
using stackchan::notifications::sanitizeRuntimeProfile;

namespace {
// 2026-11-16T12:00:00Z
constexpr auto now_ms = 1'794'830'400'000ULL;
constexpr auto expires_ms = 1'794'916'800'000ULL;  // 2026-11-17T12:00:00Z

void expect(bool passed, const char* message)
{
    if (!passed) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

PolicyLeaseBinding sampleLease()
{
    PolicyLeaseBinding lease{};
    std::strcpy(lease.policy_id.data(), "desk");
    std::strcpy(lease.version.data(), "v1");
    std::strcpy(lease.privacy_mode.data(), "private");
    lease.expires_utc_ms = expires_ms;
    return lease;
}
}  // namespace

int main()
{
    StreamProvisionRequest request{
        "coordinator.example",
        8443,
        "-----BEGIN CERTIFICATE-----\nmock",
        "opaque",
        "device-a",
        7,
        sampleLease(),
        kCoreS3MvpRuntimeProfile,
        now_ms,
    };

    const auto provision = provisionDeviceStream(request);
    expect(provision.has_value(), "MVP profile and lease provision a stream config");
    expect(provision->profile.controller.capacity == 4, "MVP capacity applied");
    expect(provision->profile.controller.heartbeat_timeout_ms == 4000, "MVP heartbeat applied");
    expect(provision->profile.controller.stability_ms == 5000, "MVP stability applied");
    expect(provision->config.max_frame_bytes == 1024, "frame ceiling from profile");
    expect(provision->config.network_timeout_ms == 10000, "network timeout from profile");
    expect(provision->config.policy_version == "v1", "policy version from lease");
    expect(provision->config.policy_expires_utc_ms == expires_ms, "policy expiry from lease");
    expect(provision->config.generation == 7, "generation forwarded");
    expect(provision->config.device_id == "device-a", "device id forwarded");
    expect(provision->config.coordinator_host == "coordinator.example", "host forwarded");
    expect(provision->config.port == 8443, "port forwarded");

    auto bad_profile = request;
    bad_profile.profile.controller.capacity = NotificationController::max_capacity + 1;
    expect(!provisionDeviceStream(bad_profile), "unsanitized profile fails closed");

    auto expired = request;
    expired.now_utc_ms = expires_ms;
    expect(!provisionDeviceStream(expired), "expired lease fails closed");

    auto no_clock = request;
    no_clock.now_utc_ms = 0;
    expect(!provisionDeviceStream(no_clock), "unsynchronized clock fails closed");

    expect(sanitizeRuntimeProfile(kCoreS3MvpRuntimeProfile).has_value(), "MVP profile remains valid");
}
