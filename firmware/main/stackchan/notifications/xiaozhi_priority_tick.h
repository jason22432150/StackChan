#pragma once

#include "notification_presenter.h"

#include <cstdint>

namespace stackchan::notifications {

/**
 * 個人版 Xiaozhi 對話優先 tick（規格 §3.6）。
 *
 * - busy=true：Presenter 清屏＋停 Motion（經 forceStop）；不得新 present
 * - busy=false：僅標示 Idle，允許後續重新評估／present
 * - 不啟用通知 Audio／TTS（仍為 A0）
 * - 不寫 Flash／SD 通知歷史
 *
 * 由 tickNotificationProductRuntime 在 poll 串流前呼叫，確保搶占先於 dequeue。
 */
void applyXiaozhiPriorityTick(NotificationPresenter& presenter, bool xiaozhi_busy,
                              std::uint64_t now_ms);

/** link_anchor／測試用：回傳 busy 時是否應禁止新通知呈現。 */
bool xiaozhiPriorityBlocksPresent(const ResourceArbiter& arbiter);

}  // namespace stackchan::notifications
