#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>

namespace stackchan::notifications {

// The SNTP callback confirms the system clock has been set in this boot.
class NotificationUtcClock {
public:
    void markSynchronized() noexcept { _synchronized.store(true, std::memory_order_release); }

    std::uint64_t utcMs() const noexcept
    {
        if (!_synchronized.load(std::memory_order_acquire)) {
            return 0;
        }
        using namespace std::chrono;
        const auto utc = duration_cast<milliseconds>(system_clock::now().time_since_epoch()).count();
        return utc > 0 ? static_cast<std::uint64_t>(utc) : 0;
    }

private:
    std::atomic<bool> _synchronized{false};
};

// Implemented by the device's existing SNTP integration.
std::uint64_t notificationUtcMs() noexcept;

}  // namespace stackchan::notifications
