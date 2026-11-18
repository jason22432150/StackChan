#pragma once

#include "notice_motion_plan.h"
#include "notification_presenter.h"
#include "resource_arbiter.h"

namespace stackchan::notifications {

/**
 * 可注入的 Servo／Motion 執行埠（host 測試用 Fake；裝置端綁 GetStackChan().motion()）。
 * 實作必須尊重 isModifyLocked；不得在此開啟音訊／TTS。
 */
struct NoticeMotionSink {
    bool (*nudge)(void* ctx, const NoticeMotionCommand& cmd) = nullptr;
    void (*stop_home)(void* ctx, const NoticeMotionCommand& home) = nullptr;
    void* ctx = nullptr;

    bool valid() const { return nudge != nullptr && stop_home != nullptr; }
};

/**
 * 通知 Motion 反應器：經 ResourceArbiter::Motion 租約後才可 nudge。
 * interrupt／Xiaozhi Busy 時一律 stop_home（即使 Generation 已失效）。
 */
class NotificationMotionReactor {
public:
    using Generation = ResourceArbiter::Generation;
    using Tick = ResourceArbiter::Tick;

    explicit NotificationMotionReactor(NoticeMotionSink sink);

    /**
     * 嘗試取得 Motion 租約並執行安全轉頭。
     * 失敗不影響已呈現的 UI；回傳 false 表示未啟動動作。
     */
    bool start(ResourceArbiter& arbiter, Generation generation, NoticeKind kind, Tick now);

    /** 正常結束：回正並釋放 Motion 租約（需仍可 mayCommit）。 */
    void stop(ResourceArbiter& arbiter, Generation generation, Tick now);

    /**
     * 安全停止：一律回正硬體；若 generation 仍持有 Motion 租約則釋放。
     * 用於 interrupt／Busy（Generation 可能已失效）。
     */
    void forceStop(ResourceArbiter& arbiter, Generation generation, Tick now);

    bool isActive() const { return _active; }

private:
    NoticeMotionSink _sink;
    bool _active = false;
};

/** 裝置端：綁定 Motion（檢查 modify lock）。 */
NoticeMotionSink makeDeviceNoticeMotionSink();

}  // namespace stackchan::notifications
