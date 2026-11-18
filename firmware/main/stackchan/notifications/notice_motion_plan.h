#pragma once

#include <cstdint>

namespace stackchan::notifications {

/**
 * 個人版通知 Servo 指令（單位與原廠 Motion 相同：0.1°）。
 * 僅允許小幅轉頭；不宣稱 task.succeeded。
 */
struct NoticeMotionCommand {
    int yaw = 0;
    int pitch = 0;
    int speed = 0;
};

/** 通知動作安全邊界（比 IdleMotion 更保守）。 */
inline constexpr int kNoticeYawMin = -200;
inline constexpr int kNoticeYawMax = 200;
inline constexpr int kNoticePitchMin = 100;
inline constexpr int kNoticePitchMax = 400;
inline constexpr int kNoticeSpeedMin = 50;
inline constexpr int kNoticeSpeedMax = 300;

/**
 * success_style=true → 輕微點頭側看；false → 另一側輕看。
 * 呼叫端以 NoticeKind::Success 對應 true（僅樣式，非 task.succeeded）。
 */
NoticeMotionCommand planNoticeNudge(bool success_style);

/** 結束／中斷時回正（yaw=0，舒適 pitch）。 */
NoticeMotionCommand planNoticeHome();

/** 指令是否落在通知安全邊界內。 */
bool isNoticeMotionWithinSafeLimits(const NoticeMotionCommand& cmd);

}  // namespace stackchan::notifications
