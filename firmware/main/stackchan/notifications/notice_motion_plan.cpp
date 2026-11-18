#include "notice_motion_plan.h"

namespace stackchan::notifications {
namespace {

int clampInt(int value, int lo, int hi)
{
    if (value < lo) {
        return lo;
    }
    if (value > hi) {
        return hi;
    }
    return value;
}

NoticeMotionCommand clampCommand(NoticeMotionCommand cmd)
{
    cmd.yaw = clampInt(cmd.yaw, kNoticeYawMin, kNoticeYawMax);
    cmd.pitch = clampInt(cmd.pitch, kNoticePitchMin, kNoticePitchMax);
    cmd.speed = clampInt(cmd.speed, kNoticeSpeedMin, kNoticeSpeedMax);
    return cmd;
}

}  // namespace

NoticeMotionCommand planNoticeNudge(bool success_style)
{
    NoticeMotionCommand cmd{};
    // 約 ±15°；速度偏慢，避免搶 Xiaozhi／傷機構。
    cmd.yaw = success_style ? 150 : -150;
    cmd.pitch = 200;
    cmd.speed = 200;
    return clampCommand(cmd);
}

NoticeMotionCommand planNoticeHome()
{
    NoticeMotionCommand cmd{};
    cmd.yaw = 0;
    cmd.pitch = 200;
    cmd.speed = 250;
    return clampCommand(cmd);
}

bool isNoticeMotionWithinSafeLimits(const NoticeMotionCommand& cmd)
{
    return cmd.yaw >= kNoticeYawMin && cmd.yaw <= kNoticeYawMax && cmd.pitch >= kNoticePitchMin &&
           cmd.pitch <= kNoticePitchMax && cmd.speed >= kNoticeSpeedMin &&
           cmd.speed <= kNoticeSpeedMax;
}

}  // namespace stackchan::notifications
