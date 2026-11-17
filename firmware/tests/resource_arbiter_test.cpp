#include <cstdlib>
#include <iostream>
#include <stackchan/notifications/resource_arbiter.h>

using stackchan::notifications::ResourceArbiter;
using stackchan::notifications::resourceArbiterCommitGate;
using Resource = ResourceArbiter::Resource;
using XiaozhiActivity = ResourceArbiter::XiaozhiActivity;

namespace {
void expect(bool condition, const char* message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

/** 正常取得三資源租約並可提交可見效果。 */
void testAcquireAndCommit()
{
    ResourceArbiter arbiter;
    const auto gen = arbiter.beginPresentation(10);
    expect(gen == 1, "first presentation starts at generation 1");
    expect(arbiter.tryAcquire(gen, Resource::Ui, 10), "ui lease");
    expect(arbiter.tryAcquire(gen, Resource::Audio, 10), "audio lease");
    expect(arbiter.tryAcquire(gen, Resource::Motion, 10), "motion lease");
    expect(arbiter.mayCommit(gen, Resource::Ui, 11), "ui commit allowed");
    expect(arbiter.mayCommit(gen, Resource::Audio, 11), "audio commit allowed");
    expect(arbiter.mayCommit(gen, Resource::Motion, 11), "motion commit allowed");
    expect(resourceArbiterCommitGate(arbiter, gen, Resource::Ui, 11), "free-function gate matches");
    arbiter.release(gen, Resource::Audio);
    expect(!arbiter.mayCommit(gen, Resource::Audio, 12), "released audio cannot commit");
    expect(arbiter.mayCommit(gen, Resource::Ui, 12), "other leases remain");
}

/** T-SEC-03：取消後舊 Generation 延遲 callback 不得再產生可見效果。 */
void testCancelInvalidatesOldCallbacks()
{
    ResourceArbiter arbiter;
    const auto gen = arbiter.beginPresentation(1);
    expect(arbiter.tryAcquire(gen, Resource::Ui, 1), "ui");
    expect(arbiter.tryAcquire(gen, Resource::Audio, 1), "audio");
    expect(arbiter.tryAcquire(gen, Resource::Motion, 1), "motion");

    const auto confirmation = arbiter.cancelCurrent(2);
    expect(confirmation.invalidated_generation == gen, "confirmation names cancelled generation");
    expect(confirmation.had_ui && confirmation.had_audio && confirmation.had_motion, "leases recorded");
    expect(confirmation.generation_bumped, "generation bumped immediately");
    expect(arbiter.currentGeneration() == gen + 1, "new generation is active");

    // 延遲到達的舊 callback：不可 commit、不可重新取得舊 generation 租約。
    expect(!arbiter.mayCommit(gen, Resource::Ui, 3), "stale ui callback blocked");
    expect(!arbiter.mayCommit(gen, Resource::Audio, 3), "stale audio callback blocked");
    expect(!arbiter.mayCommit(gen, Resource::Motion, 3), "stale motion callback blocked");
    expect(!arbiter.tryAcquire(gen, Resource::Ui, 3), "stale acquire rejected");
    expect(!resourceArbiterCommitGate(arbiter, gen, Resource::Ui, 3), "gate rejects stale generation");

    // bump 後的新 Generation 可取三資源（正式路徑仍應再 beginPresentation）。
    const auto next = arbiter.currentGeneration();
    expect(arbiter.tryAcquire(next, Resource::Ui, 3), "new generation can acquire ui");
    expect(arbiter.tryAcquire(next, Resource::Audio, 3), "new generation can acquire audio");
}

/** Fail-Closed revokeAll 與時鐘倒退。 */
void testRevokeAllAndClockRegression()
{
    ResourceArbiter arbiter;
    const auto gen = arbiter.beginPresentation(5);
    expect(arbiter.tryAcquire(gen, Resource::Ui, 5), "ui");
    const auto revoked = arbiter.revokeAll(6);
    expect(revoked.generation_bumped && revoked.had_ui, "revoke confirms ui lease");
    expect(!arbiter.mayCommit(gen, Resource::Ui, 7), "revoked generation cannot commit");

    const auto gen2 = arbiter.beginPresentation(8);
    expect(arbiter.tryAcquire(gen2, Resource::Audio, 8), "fresh audio");
    // 時鐘倒退：noteTick 會 bump generation 並清租約。
    expect(!arbiter.mayCommit(gen2, Resource::Audio, 7), "const gate sees clock regression");
    arbiter.tryAcquire(gen2, Resource::Ui, 7);  // 觸發非 const 倒退處理
    expect(arbiter.currentGeneration() != gen2, "clock regression bumps generation");
    expect(!arbiter.hasLease(Resource::Audio), "leases cleared on regression");
}

/** Xiaozhi Busy 搶占：Audio／Motion／UI 立即讓出；Idle 後可重取同一 Generation。 */
void testXiaozhiPreemption()
{
    ResourceArbiter arbiter;
    const auto gen = arbiter.beginPresentation(1);
    expect(arbiter.tryAcquire(gen, Resource::Ui, 1), "ui");
    expect(arbiter.tryAcquire(gen, Resource::Audio, 1), "audio");
    expect(arbiter.tryAcquire(gen, Resource::Motion, 1), "motion");

    arbiter.onXiaozhiActivity(XiaozhiActivity::Busy, 2);
    expect(arbiter.xiaozhiActivity() == XiaozhiActivity::Busy, "busy recorded");
    expect(!arbiter.mayCommit(gen, Resource::Ui, 2), "ui yielded");
    expect(!arbiter.mayCommit(gen, Resource::Audio, 2), "audio revoked");
    expect(!arbiter.mayCommit(gen, Resource::Motion, 2), "motion revoked");
    expect(!arbiter.tryAcquire(gen, Resource::Audio, 2), "busy denies audio acquire");
    expect(arbiter.currentGeneration() == gen, "preemption keeps generation for re-eval");

    arbiter.onXiaozhiActivity(XiaozhiActivity::Idle, 3);
    expect(arbiter.tryAcquire(gen, Resource::Ui, 3), "idle allows ui re-acquire");
    expect(arbiter.tryAcquire(gen, Resource::Audio, 3), "idle allows audio re-acquire");
    expect(arbiter.mayCommit(gen, Resource::Audio, 3), "post-dialog commit allowed");
}

/** 新 beginPresentation 使上一輪 Generation 全部失效。 */
void testNewPresentationInvalidatesPrevious()
{
    ResourceArbiter arbiter;
    const auto first = arbiter.beginPresentation(1);
    expect(arbiter.tryAcquire(first, Resource::Ui, 1), "first ui");
    const auto second = arbiter.beginPresentation(2);
    expect(second == first + 1, "presentation bumps generation");
    expect(!arbiter.mayCommit(first, Resource::Ui, 2), "previous generation blocked");
    expect(!arbiter.hasLease(Resource::Ui), "leases reset on new presentation");
    expect(arbiter.tryAcquire(second, Resource::Ui, 2), "new generation can acquire");
}
}  // namespace

int main()
{
    testAcquireAndCommit();
    testCancelInvalidatesOldCallbacks();
    testRevokeAllAndClockRegression();
    testXiaozhiPreemption();
    testNewPresentationInvalidatesPrevious();
    return 0;
}
