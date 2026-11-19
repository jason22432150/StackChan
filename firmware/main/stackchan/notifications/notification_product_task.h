#pragma once

#include <cstdint>
#include <array>
#include <string>
#include <string_view>

#include "notification_product_runtime.h"
#include "personal_pending_boot.h"

namespace stackchan::notifications {

// Local task-context request. True means the worker started, not that TLS
// succeeded. One worker owns the runtime until bootstrap fails or disconnects.
bool requestNotificationProductStream(std::uint64_t coordinator_generation);

enum class NotificationPairingState { Idle, Starting, AwaitingApproval, Connecting, Connected, Failed, Cancelled };

struct NotificationPairingStatus {
    NotificationPairingState state = NotificationPairingState::Idle;
    std::array<char, 7> user_code{};
};

// Nonblocking local request. Uses the same exclusive worker as notifications.
bool requestNotificationProductPairing(NotificationPairingEndpoint endpoint, std::uint16_t stream_port,
                                       std::uint64_t coordinator_generation);
NotificationPairingStatus notificationProductPairingStatus();
// Applies until Connecting. In-flight HTTPS returns before cancellation completes.
void cancelNotificationProductPairing() noexcept;

enum class NotificationStreamRequestResult { InvalidGeneration, Rejected, Scheduled };

NotificationStreamRequestResult requestConfiguredNotificationProductStream(std::string_view generation);
void publishNotificationXiaozhiBusy(bool busy) noexcept;

}  // namespace stackchan::notifications
