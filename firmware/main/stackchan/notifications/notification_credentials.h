#pragma once

#include <cstdint>
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

// Reads the agent_notify namespace in the initialized, encrypted default NVS.
// Any missing or invalid field returns nullopt. TLS and policy validation are
// still required before using the returned fields to provision a stream.
std::optional<NotificationCredentials> loadNotificationCredentials();

}  // namespace stackchan::notifications
