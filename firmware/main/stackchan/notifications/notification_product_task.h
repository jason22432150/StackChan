#pragma once

#include <cstdint>

namespace stackchan::notifications {

// Local task-context request. True means the worker started, not that TLS
// succeeded. One worker owns the runtime until bootstrap fails or disconnects.
bool requestNotificationProductStream(std::uint64_t coordinator_generation);
void publishNotificationXiaozhiBusy(bool busy) noexcept;

}  // namespace stackchan::notifications
