#pragma once

#include "notification_presenter.h"

namespace stackchan::notifications {

/**
 * 裝置端：綁定既有 `Hal::lvglLock`／`lvglUnlock`（與 `LvglLockGuard` 相同路徑）。
 * 僅韌體建置；host CTest 不編譯此翻譯單元。
 */
LvglLockHooks makeHalLvglLockHooks();

}  // namespace stackchan::notifications
