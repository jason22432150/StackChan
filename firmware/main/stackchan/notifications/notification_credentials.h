#pragma once

#include <cstdint>
#include <mutex>
#include <optional>
#include <string>

namespace stackchan::notifications {

struct NotificationCredentials {
    std::string coordinator_host;
    std::uint16_t port = 0;
    std::string coordinator_ca_pem;
    std::string token;
    std::string device_id;
};

struct NotificationCredentialLease {
    NotificationCredentials credentials;
    std::uint64_t expires_at_utc_ms = 0;
};

// An in-memory handoff from local pairing to the stream bootstrap task.
// The consumer takes ownership once, including the original grant expiry.
class PendingNotificationCredentials {
public:
    bool stage(NotificationCredentialLease lease, std::uint64_t now_utc_ms);
    std::optional<NotificationCredentialLease> take(std::uint64_t now_utc_ms);
    void clear();

private:
    std::mutex _mutex;
    std::optional<NotificationCredentialLease> _pending;
    std::uint64_t _staged_at_utc_ms = 0;
};

// Reads the agent_notify namespace in the initialized, encrypted default NVS.
// Any missing or invalid field returns nullopt. TLS and policy validation are
// still required before using the returned fields to provision a stream.
std::optional<NotificationCredentials> loadNotificationCredentials();

}  // namespace stackchan::notifications
