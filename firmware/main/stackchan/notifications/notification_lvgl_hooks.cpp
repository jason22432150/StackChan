#include "notification_lvgl_hooks.h"

#include "hal/hal.h"

namespace stackchan::notifications {
namespace {

void lockHal(void* /*ctx*/)
{
    GetHAL().lvglLock();
}

void unlockHal(void* /*ctx*/)
{
    GetHAL().lvglUnlock();
}

}  // namespace

LvglLockHooks makeHalLvglLockHooks()
{
    // 與 LvglLockGuard 使用同一對 lock／unlock，絕不另開平行顯示鎖。
    return LvglLockHooks{lockHal, unlockHal, nullptr};
}

}  // namespace stackchan::notifications
