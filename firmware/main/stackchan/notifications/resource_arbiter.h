#pragma once

#include <cstdint>
#include <optional>

namespace stackchan::notifications {

/**
 * P2-05：通知對 UI／Audio／Motion 的 Generation Token 授權閘門。
 *
 * 單一執行上下文使用。Transport／非同步回呼在提交任何可見效果前必須呼叫
 * mayCommit；安全撤銷先同步失效 Generation，不等待子系統 Cancellation ACK
 * （D-087／D-088、不變式 #2／#7、T-SEC-03）。
 *
 * 不取代 Xiaozhi 原廠音訊最高控制權：Busy 時立即撤銷通知 Audio／Motion，
 * UI 讓出；Idle 後同一 Generation 可重新 tryAcquire（對話後重評估由上層做）。
 */
class ResourceArbiter {
public:
    using Generation = std::uint64_t;
    using Tick = std::uint64_t;

    enum class Resource : std::uint8_t { Ui = 0, Audio = 1, Motion = 2 };
    enum class XiaozhiActivity : std::uint8_t { Idle, Busy };

    struct CancelConfirmation {
        Generation invalidated_generation = 0;
        bool had_ui = false;
        bool had_audio = false;
        bool had_motion = false;
        bool generation_bumped = false;
    };

    ResourceArbiter() = default;

    /**
     * 開始一輪通知呈現，回傳新的 Generation；0 保留為無效。
     * 每一輪可見呈現都應先呼叫此函式，再 tryAcquire（含 cancel／revoke 之後）。
     */
    Generation beginPresentation(Tick now);

    /**
     * 在有效 Generation 下取得資源租約。
     * Xiaozhi Busy 時拒絕 Audio／Motion；UI 在 Busy 時也拒絕（讓出畫面）。
     */
    bool tryAcquire(Generation generation, Resource resource, Tick now);

    /** 正常完成時釋放單一資源，不 bump Generation。 */
    void release(Generation generation, Resource resource);

    /**
     * 提交可見效果前的閘門（舊 callback 失效點）。
     * Generation 失效、無租約、或 Xiaozhi Busy 讓出時皆回 false。
     */
    bool mayCommit(Generation generation, Resource resource, Tick now) const;

    /**
     * 取消目前呈現：同步撤銷三資源租約並 bump Generation，立即回傳確認。
     * 不阻塞等待 UI／Audio／Motion 子系統 ACK。
     */
    CancelConfirmation cancelCurrent(Tick now);

    /** Fail-Closed 安全撤銷（失聯／政策失效）：等同 cancelCurrent。 */
    CancelConfirmation revokeAll(Tick now);

    /** Xiaozhi 搶占：Busy 立即撤銷 Audio／Motion 並讓出 UI；Idle 僅更新狀態。 */
    void onXiaozhiActivity(XiaozhiActivity activity, Tick now);

    Generation currentGeneration() const { return _generation; }
    XiaozhiActivity xiaozhiActivity() const { return _xiaozhi; }
    bool hasLease(Resource resource) const;

private:
    void clearLease(Resource resource);
    void noteTick(Tick now);

    Generation _generation = 0;
    XiaozhiActivity _xiaozhi = XiaozhiActivity::Idle;
    bool _lease_ui = false;
    bool _lease_audio = false;
    bool _lease_motion = false;
    bool _ui_yielded = false;
    Tick _last_tick = 0;
};

/**
 * 連結保留／測試用的自由函式閘門；行為等同 mayCommit。
 * link_anchor 只取位址，執行期不得由此啟動 Xiaozhi／LVGL。
 */
bool resourceArbiterCommitGate(const ResourceArbiter& arbiter, ResourceArbiter::Generation generation,
                               ResourceArbiter::Resource resource, ResourceArbiter::Tick now);

}  // namespace stackchan::notifications
