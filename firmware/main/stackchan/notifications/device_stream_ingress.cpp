#include "device_stream_ingress.h"

#include <algorithm>
#include <limits>

namespace stackchan::notifications {
namespace {
bool copyIdentifier(std::string_view id, std::array<char, NotificationController::max_id_bytes + 1>& output)
{
    if (id.empty() || id.size() >= output.size() || id.find('\0') != std::string_view::npos) {
        return false;
    }
    output.fill('\0');
    std::copy(id.begin(), id.end(), output.begin());
    return true;
}
}  // namespace

DeviceStreamIngress::DeviceStreamIngress(NotificationController& controller, Tick max_frame_age_ms)
    : _controller(controller), _max_frame_age(max_frame_age_ms)
{
}

bool DeviceStreamIngress::bindVerified(VerifiedBinding binding, Tick utc_ms, Tick now)
{
    if (binding.session <= _session) {
        return false;
    }
    disconnect(_session);
    _session = binding.session;
    if (_max_frame_age == 0 || utc_ms == 0 || binding.policy_expires_utc_ms <= utc_ms ||
        !copyIdentifier(binding.device_id, _device) || !copyIdentifier(binding.policy_version, _policy)) {
        return false;
    }
    const auto lifetime = binding.policy_expires_utc_ms - utc_ms;
    if (lifetime > std::numeric_limits<Tick>::max() - now ||
        !_controller.beginRecovery(_session, _policy.data(), now + lifetime, now)) {
        return false;
    }
    _bound_at = now;
    _bound_utc = utc_ms;
    _generation = binding.generation;
    _last_heartbeat_utc = 0;
    _bound = true;
    return true;
}

void DeviceStreamIngress::disconnect(SessionId session)
{
    if (session == _session) {
        _bound = false;
        _controller.suspend(session);
    }
}

bool DeviceStreamIngress::accepts(Frame frame, Tick now)
{
    if (!_bound || frame.session != _session) {
        return false;
    }
    if (now < _bound_at || now - _bound_at > std::numeric_limits<Tick>::max() - _bound_utc ||
        _controller.state(now) == NotificationController::State::Suspended) {
        disconnect(_session);
        return false;
    }
    const auto estimated_utc = _bound_utc + (now - _bound_at);
    return frame.device_id == _device.data() && frame.policy_version == _policy.data() &&
           frame.generation == _generation && frame.sent_utc_ms >= _bound_utc &&
           frame.sent_utc_ms <= estimated_utc && estimated_utc - frame.sent_utc_ms <= _max_frame_age;
}

bool DeviceStreamIngress::receiveHeartbeat(Frame frame, Tick now)
{
    if (!accepts(frame, now) || frame.sent_utc_ms <= _last_heartbeat_utc) {
        return false;
    }
    if (!_controller.heartbeat(_session, now)) {
        return false;
    }
    _last_heartbeat_utc = frame.sent_utc_ms;
    return true;
}

bool DeviceStreamIngress::receiveIntent(Frame frame, std::string_view delivery_id, Tick expires_utc_ms, Tick now)
{
    if (!accepts(frame, now)) {
        return false;
    }
    const auto estimated_utc = _bound_utc + (now - _bound_at);
    if (expires_utc_ms <= estimated_utc || expires_utc_ms - estimated_utc > std::numeric_limits<Tick>::max() - now) {
        return false;
    }
    return _controller.enqueue(_session, _policy.data(), delivery_id, now + (expires_utc_ms - estimated_utc), now);
}

}  // namespace stackchan::notifications
