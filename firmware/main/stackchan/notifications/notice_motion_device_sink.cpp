#include "notification_motion_reactor.h"

#include <stackchan/stackchan.h>

namespace stackchan::notifications {
namespace {

bool deviceNudge(void* /*ctx*/, const NoticeMotionCommand& cmd)
{
    if (!isNoticeMotionWithinSafeLimits(cmd)) {
        return false;
    }
    auto& stackchan = GetStackChan();
    auto& motion = stackchan.motion();
    // 布林 modify lock 不是完整 Mutex；鎖定時拒絕，避免與 IMU／Xiaozhi 衝突。
    if (motion.isModifyLocked()) {
        return false;
    }
    motion.moveWithSpeed(cmd.yaw, cmd.pitch, cmd.speed);
    return true;
}

void deviceStopHome(void* /*ctx*/, const NoticeMotionCommand& home)
{
    auto& motion = GetStackChan().motion();
    // locked／非法指令：只 stop() 止血，不與 IMU／Xiaozhi 搶 lock 硬回正。
    if (!isNoticeMotionWithinSafeLimits(home) || motion.isModifyLocked()) {
        motion.stop();
        return;
    }
    motion.moveWithSpeed(home.yaw, home.pitch, home.speed);
}

}  // namespace

NoticeMotionSink makeDeviceNoticeMotionSink()
{
    return NoticeMotionSink{deviceNudge, deviceStopHome, nullptr};
}

}  // namespace stackchan::notifications
