#include "notification_controller.h"

#include <algorithm>

namespace stackchan::notifications {
namespace {
bool validIdentifier(std::string_view id)
{
    return !id.empty() && id.size() <= NotificationController::max_id_bytes &&
           id.find('\0') == std::string_view::npos;
}
}  // namespace

NotificationController::NotificationController(Limits limits) : _limits(limits)
{
}

bool NotificationController::beginRecovery(
    SessionId session, std::string_view policy_version, Tick policy_until, Tick now)
{
    if (session <= _session) {
        return false;
    }
    suspend(_session);
    _session = session;
    if (now < _last_tick || policy_until <= now || !validIdentifier(policy_version) ||
        _limits.capacity == 0 || _limits.capacity > max_capacity ||
        _limits.heartbeat_timeout_ms == 0 || _limits.stability_ms == 0) {
        return false;
    }
    _last_tick = now;
    _policy_version.fill('\0');
    std::copy(policy_version.begin(), policy_version.end(), _policy_version.begin());
    _policy_until = policy_until;
    _connected_at = _last_heartbeat = now;
    _state = State::Recovering;
    return true;
}

NotificationController::State NotificationController::state(Tick now)
{
    if (now < _last_tick) {
        suspend(_session);
        return _state;
    }
    _last_tick = now;
    if (_state != State::Suspended &&
        (now >= _policy_until || now - _last_heartbeat >= _limits.heartbeat_timeout_ms)) {
        suspend(_session);
    }
    return _state;
}

bool NotificationController::heartbeat(SessionId session, Tick now)
{
    if (session != _session || state(now) == State::Suspended) {
        return false;
    }
    _last_heartbeat = now;
    if (now - _connected_at >= _limits.stability_ms) {
        _state = State::Active;
    }
    return true;
}

void NotificationController::suspend(SessionId session)
{
    if (session == _session) {
        _state = State::Suspended;
        _queue.fill(PendingDelivery{});
        _size = 0;
    }
}

bool NotificationController::enqueue(
    SessionId session, std::string_view policy_version, std::string_view id, Tick expires_at, Tick now)
{
    if (session != _session || state(now) != State::Active ||
        policy_version != _policy_version.data() || !validIdentifier(id) || expires_at <= now) {
        return false;
    }
    discardExpired(now);
    if (_size == _limits.capacity ||
        std::any_of(_queue.begin(), _queue.begin() + _size,
                    [id](const PendingDelivery& entry) { return id == entry.id.data(); })) {
        return false;
    }
    auto& entry = _queue[_size++];
    std::copy(id.begin(), id.end(), entry.id.begin());
    entry.expires_at = expires_at;
    return true;
}

std::optional<NotificationController::PendingDelivery> NotificationController::takeNext(SessionId session, Tick now)
{
    if (session != _session || state(now) != State::Active) {
        return std::nullopt;
    }
    discardExpired(now);
    if (_size == 0) {
        return std::nullopt;
    }
    auto next = _queue.front();
    std::move(_queue.begin() + 1, _queue.begin() + _size, _queue.begin());
    _queue[--_size] = {};
    return next;
}

void NotificationController::discardExpired(Tick now)
{
    auto previous_end = _queue.begin() + _size;
    auto end = std::remove_if(_queue.begin(), previous_end,
                              [now](const PendingDelivery& entry) { return entry.expires_at <= now; });
    std::fill(end, previous_end, PendingDelivery{});
    _size = static_cast<std::size_t>(end - _queue.begin());
}

}  // namespace stackchan::notifications
