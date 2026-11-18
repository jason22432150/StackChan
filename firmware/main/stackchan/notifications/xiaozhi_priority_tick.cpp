#include "xiaozhi_priority_tick.h"

namespace stackchan::notifications {

void applyXiaozhiPriorityTick(NotificationPresenter& presenter, bool xiaozhi_busy, std::uint64_t now_ms)
{
    const auto activity = xiaozhi_busy ? ResourceArbiter::XiaozhiActivity::Busy
                                       : ResourceArbiter::XiaozhiActivity::Idle;
    // 先於串流 poll／dequeue：Busy 必須立刻讓出 UI／Motion。
    presenter.onXiaozhiActivity(activity, now_ms);
}

bool xiaozhiPriorityBlocksPresent(const ResourceArbiter& arbiter)
{
    return arbiter.xiaozhiActivity() == ResourceArbiter::XiaozhiActivity::Busy;
}

}  // namespace stackchan::notifications
