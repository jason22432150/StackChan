#include <cstdlib>
#include <iostream>

#include <stackchan/notifications/notice_motion_plan.h>

using stackchan::notifications::NoticeMotionCommand;
using stackchan::notifications::isNoticeMotionWithinSafeLimits;
using stackchan::notifications::kNoticeSpeedMax;
using stackchan::notifications::kNoticeYawMax;
using stackchan::notifications::kNoticeYawMin;
using stackchan::notifications::planNoticeHome;
using stackchan::notifications::planNoticeNudge;

namespace {

void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

void testNudgeDirections()
{
    const auto success = planNoticeNudge(true);
    const auto neutral = planNoticeNudge(false);
    expect(success.yaw > 0 && neutral.yaw < 0, "opposite yaw sides");
    expect(isNoticeMotionWithinSafeLimits(success), "success safe");
    expect(isNoticeMotionWithinSafeLimits(neutral), "neutral safe");
    expect(success.speed <= kNoticeSpeedMax, "speed capped");
}

void testHomeCentered()
{
    const auto home = planNoticeHome();
    expect(home.yaw == 0, "home yaw");
    expect(isNoticeMotionWithinSafeLimits(home), "home safe");
}

void testRejectsOutOfRange()
{
    NoticeMotionCommand bad{kNoticeYawMax + 1, 200, 200};
    expect(!isNoticeMotionWithinSafeLimits(bad), "yaw over");
    NoticeMotionCommand bad2{kNoticeYawMin, 200, kNoticeSpeedMax + 1};
    expect(!isNoticeMotionWithinSafeLimits(bad2), "speed over");
}

}  // namespace

int main()
{
    testNudgeDirections();
    testHomeCentered();
    testRejectsOutOfRange();
    return 0;
}
