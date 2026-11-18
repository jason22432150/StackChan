#include "notification_motion_reactor.h"

namespace stackchan::notifications {

NotificationMotionReactor::NotificationMotionReactor(NoticeMotionSink sink) : _sink(sink) {}

bool NotificationMotionReactor::start(ResourceArbiter& arbiter, Generation generation, NoticeKind kind,
                                      Tick now)
{
    if (!_sink.valid() || generation == 0) {
        return false;
    }
    if (arbiter.xiaozhiActivity() == ResourceArbiter::XiaozhiActivity::Busy) {
        return false;
    }
    if (!arbiter.tryAcquire(generation, ResourceArbiter::Resource::Motion, now)) {
        return false;
    }
    if (!arbiter.mayCommit(generation, ResourceArbiter::Resource::Motion, now)) {
        arbiter.release(generation, ResourceArbiter::Resource::Motion);
        return false;
    }

    const auto cmd = planNoticeNudge(kind == NoticeKind::Success);
    if (!isNoticeMotionWithinSafeLimits(cmd) || !_sink.nudge(_sink.ctx, cmd)) {
        arbiter.release(generation, ResourceArbiter::Resource::Motion);
        return false;
    }
    _active = true;
    return true;
}

void NotificationMotionReactor::stop(ResourceArbiter& arbiter, Generation generation, Tick now)
{
    if (!_active) {
        return;
    }
    const auto home = planNoticeHome();
    if (_sink.valid()) {
        _sink.stop_home(_sink.ctx, home);
    }
    _active = false;
    if (generation != 0 && arbiter.mayCommit(generation, ResourceArbiter::Resource::Motion, now)) {
        arbiter.release(generation, ResourceArbiter::Resource::Motion);
    }
}

void NotificationMotionReactor::forceStop(ResourceArbiter& arbiter, Generation generation, Tick now)
{
    if (!_active && !arbiter.hasLease(ResourceArbiter::Resource::Motion)) {
        return;
    }
    const auto home = planNoticeHome();
    if (_sink.valid()) {
        _sink.stop_home(_sink.ctx, home);
    }
    _active = false;
    // Generation 可能已 bump；仍嘗試釋放目前租約狀態。
    if (arbiter.hasLease(ResourceArbiter::Resource::Motion)) {
        if (generation != 0 && arbiter.mayCommit(generation, ResourceArbiter::Resource::Motion, now)) {
            arbiter.release(generation, ResourceArbiter::Resource::Motion);
        } else {
            // 租約殘留但不可 commit：靠 cancel／Busy 路徑已 clearLease；此處僅清本地旗標。
            (void)now;
        }
    }
}

}  // namespace stackchan::notifications
