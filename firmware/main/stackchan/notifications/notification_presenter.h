#pragma once

#include "resource_arbiter.h"

#include <cstddef>
#include <cstdint>
#include <string_view>

namespace stackchan::notifications {

/** P2-06：基礎通知視覺種類（不推導 task.succeeded；Success 僅表示成功樣式）。 */
enum class NoticeKind : std::uint8_t { Neutral = 0, Success = 1 };

/**
 * 通知 UI 後端。實作不得在回呼內做網路／SD 解碼。
 * 真正 LVGL 更新必須經 LvglLockedUiPort（對齊 LvglLockGuard）。
 */
class NotificationUiPort {
public:
    virtual ~NotificationUiPort() = default;
    virtual bool show(NoticeKind kind, std::string_view text) = 0;
    virtual void clear() = 0;
};

/**
 * LVGL 鎖 hooks：語意對齊 `LvglLockGuard`（ctor lock／dtor unlock）。
 * 裝置端可綁定 Hal::lvglLock／lvglUnlock；host 測試注入計數替身。
 */
struct LvglLockHooks {
    void (*lock)(void* ctx) = nullptr;
    void (*unlock)(void* ctx) = nullptr;
    void* ctx = nullptr;

    bool valid() const { return lock != nullptr && unlock != nullptr; }
};

/** 在 LVGL lock 內轉呼叫內層 sink；鎖失敗則拒絕 show（Fail-Closed）。 */
class LvglLockedUiPort final : public NotificationUiPort {
public:
    LvglLockedUiPort(NotificationUiPort& inner, LvglLockHooks hooks);

    bool show(NoticeKind kind, std::string_view text) override;
    void clear() override;

private:
    NotificationUiPort& _inner;
    LvglLockHooks _hooks;
};

/**
 * P2-06：經 ResourceArbiter 授權後呈現中性／成功通知。
 *
 * - 可見效果前必須 mayCommit(Ui)
 * - 撤銷／Xiaozhi Busy：先 arbiter 同步失效，再 clear（clear 不需租約）
 * - 不持 LVGL lock 呼叫 arbiter；不繞過 Xiaozhi（Busy 時拒絕 present）
 */
class NotificationPresenter {
public:
    static constexpr std::size_t max_text_bytes = 128;

    using Generation = ResourceArbiter::Generation;
    using Tick = ResourceArbiter::Tick;

    NotificationPresenter(ResourceArbiter& arbiter, NotificationUiPort& ui);

    /** 開始呈現；成功後持有 UI 租約並留下可見狀態。 */
    bool present(NoticeKind kind, std::string_view text, Tick now);

    /** 正常結束：清屏並釋放 UI 租約（不 bump Generation）。 */
    void dismiss(Tick now);

    /**
     * 安全中斷：cancelCurrent＋清屏。
     * 回傳 arbiter 取消確認（不等待子系統 ACK）。
     */
    ResourceArbiter::CancelConfirmation interrupt(Tick now);

    /** Xiaozhi 搶占：轉發 Busy／Idle；Busy 時若可見則清屏。 */
    void onXiaozhiActivity(ResourceArbiter::XiaozhiActivity activity, Tick now);

    bool isVisible() const { return _visible; }
    Generation generation() const { return _generation; }
    NoticeKind kind() const { return _kind; }

private:
    bool textAllowed(std::string_view text) const;

    ResourceArbiter& _arbiter;
    NotificationUiPort& _ui;
    Generation _generation = 0;
    NoticeKind _kind = NoticeKind::Neutral;
    bool _visible = false;
};

/** link_anchor 保留用；回傳 present 是否允許的預檢（不執行 UI）。 */
bool notificationPresenterMayPresent(const ResourceArbiter& arbiter, ResourceArbiter::Generation generation,
                                     ResourceArbiter::Tick now);

}  // namespace stackchan::notifications
