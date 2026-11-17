#pragma once

#include <cstdint>
#include <string_view>

namespace stackchan::notifications {

// Local task-context request. True means the worker started, not that TLS
// succeeded. One worker owns the runtime until bootstrap fails or disconnects.
bool requestNotificationProductStream(std::uint64_t coordinator_generation);

enum class NotificationStreamRequestResult { InvalidGeneration, Rejected, Scheduled };

NotificationStreamRequestResult requestConfiguredNotificationProductStream(std::string_view generation);
void publishNotificationXiaozhiBusy(bool busy) noexcept;

}  // namespace stackchan::notifications
