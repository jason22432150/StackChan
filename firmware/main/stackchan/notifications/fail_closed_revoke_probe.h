#pragma once

#include "fail_closed_budget.h"
#include "fail_closed_guard.h"
#include "notification_controller.h"
#include "notification_presenter.h"
#include "presentation_receipt.h"
#include "resource_arbiter.h"

#include <cstdint>
#include <optional>

namespace stackchan::notifications {

/**
 * R-006 實機／host 量測：在真實 poll 節奏下量測「最後心跳 → Fail-Closed 清屏」壁鐘。
 *
 * 不呼叫 Xiaozhi／AudioCodec／Servo。UI 由呼叫端注入（裝置可用 FakeUi＋LVGL lock hooks）。
 * 單次量測完成後進入 Done；不會自動重跑。
 */
struct FailClosedRevokeSample {
    std::uint64_t last_heartbeat_ms = 0;
    std::uint64_t revoked_at_ms = 0;
    std::uint64_t revoke_ms = 0;
    std::uint64_t budget_ms = kMvpSoftWorstCaseRevokeMs;
    bool interrupted = false;
    bool within_budget = false;
};

class FailClosedRevokeProbe {
public:
    using Tick = NotificationController::Tick;

    FailClosedRevokeProbe(NotificationUiPort& ui, LvglLockHooks locks,
                          NotificationController::Limits limits = {4, 4000, 5},
                          Tick budget_ms = kMvpSoftWorstCaseRevokeMs);

    /** 每個控制迴圈呼叫一次；回傳 true 表示本輪剛產出樣本。 */
    bool poll(Tick now_ms);

    const std::optional<FailClosedRevokeSample>& sample() const { return _sample; }
    bool done() const { return _phase == Phase::Done; }

private:
    enum class Phase { Arm, Show, WaitSilence, Done };

    NotificationController _controller;
    ResourceArbiter _arbiter;
    LvglLockedUiPort _ui;
    NotificationPresenter _presenter;
    PresentationReceiptTracker _receipts;
    FailClosedGuard _guard;
    const Tick _budget_ms;
    Phase _phase = Phase::Arm;
    Tick _last_heartbeat_ms = 0;
    std::optional<FailClosedRevokeSample> _sample;
};

/** link_anchor／測試：確認量測進入點已連結。 */
bool failClosedRevokeProbeLinked();

}  // namespace stackchan::notifications
