#include "personal_pending_ingress.h"

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

PersonalPendingIngress::PersonalPendingIngress(NotificationController& controller, Tick max_skew_ms)
    : _controller(controller), _max_skew(max_skew_ms)
{
}

bool PersonalPendingIngress::bind(Binding binding, Tick utc_ms, Tick now)
{
    if (binding.session <= _session) {
        return false;
    }
    disconnect(_session);
    _session = binding.session;
    if (_max_skew == 0 || utc_ms == 0 || binding.policy_expires_utc_ms <= utc_ms ||
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
    _last_pulse_utc = 0;
    _bound = true;
    return true;
}

void PersonalPendingIngress::disconnect(SessionId session)
{
    if (session == _session) {
        _bound = false;
        _controller.suspend(session);
    }
}

bool PersonalPendingIngress::clockOk(Tick now) const
{
    if (!_bound || now < _bound_at ||
        now - _bound_at > std::numeric_limits<Tick>::max() - _bound_utc ||
        _controller.state(now) == NotificationController::State::Suspended) {
        return false;
    }
    return true;
}

bool PersonalPendingIngress::pulse(Tick observed_utc_ms, Tick now)
{
    if (!clockOk(now)) {
        disconnect(_session);
        return false;
    }
    // 以 bind 時 (utc, mono) 推估當前 UTC；允許前後對稱 _max_skew。
    // 舊邏輯拒「超前 1ms」會在 SNTP／system_clock 與 esp_timer 不同步時誤殺 worker。
    const auto estimated_utc = _bound_utc + (now - _bound_at);
    if (observed_utc_ms < _bound_utc || observed_utc_ms <= _last_pulse_utc) {
        return false;
    }
    const auto delta = observed_utc_ms > estimated_utc ? observed_utc_ms - estimated_utc
                                                       : estimated_utc - observed_utc_ms;
    if (delta > _max_skew) {
        return false;
    }
    if (!_controller.heartbeat(_session, now)) {
        return false;
    }
    _last_pulse_utc = observed_utc_ms;
    return true;
}

bool PersonalPendingIngress::receiveItem(std::string_view device_id, std::string_view policy_version,
                                         std::uint64_t generation, std::string_view delivery_id,
                                         Tick expires_utc_ms, Tick now)
{
    if (!clockOk(now) || device_id != _device.data() || policy_version != _policy.data() ||
        generation != _generation) {
        return false;
    }
    const auto estimated_utc = _bound_utc + (now - _bound_at);
    if (expires_utc_ms <= estimated_utc ||
        expires_utc_ms - estimated_utc > std::numeric_limits<Tick>::max() - now) {
        return false;
    }
    return _controller.enqueue(_session, _policy.data(), delivery_id, now + (expires_utc_ms - estimated_utc),
                               now);
}

}  // namespace stackchan::notifications
