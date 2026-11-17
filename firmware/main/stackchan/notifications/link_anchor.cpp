/*
 * P2-04 link retain：全量韌體在 --gc-sections 下會丟棄尚無呼叫端的 notifications。
 * 此檔只以函式位址建立 GC root（CMake 以 -u 強制拉入），絕不執行網路／UI／Xiaozhi 路徑。
 */
#include "policy_lease.h"
#include "resource_arbiter.h"
#include "runtime_limits.h"
#include "stream_bootstrap.h"
#include "stream_session_start.h"

namespace {

using RetainFn = const void*;
using stackchan::notifications::fetchAndProvisionDeviceStream;
using stackchan::notifications::parsePolicyLeaseJson;
using stackchan::notifications::resourceArbiterCommitGate;
using stackchan::notifications::sanitizeRuntimeProfile;
using stackchan::notifications::startProvisionedDeviceStream;

const RetainFn kMvpLinkRetain[] = {
    reinterpret_cast<RetainFn>(&sanitizeRuntimeProfile),
    reinterpret_cast<RetainFn>(&parsePolicyLeaseJson),
    reinterpret_cast<RetainFn>(&fetchAndProvisionDeviceStream),
    reinterpret_cast<RetainFn>(&startProvisionedDeviceStream),
    reinterpret_cast<RetainFn>(&resourceArbiterCommitGate),
};

}  // namespace

// 連結器 -u 的 GC root；讀取表避免編譯器刪除 kMvpLinkRetain。
extern "C" const void* const stackchan_notifications_mvp_retain = &kMvpLinkRetain[0];
