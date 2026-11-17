#include "notification_presenter.h"

namespace stackchan::notifications {
namespace {

bool jsonSafeText(std::string_view text)
{
    for (unsigned char c : text) {
        if (c < 0x20 || c == '"' || c == '\\') {
            return false;
        }
    }
    return true;
}

}  // namespace

LvglLockedUiPort::LvglLockedUiPort(NotificationUiPort& inner, LvglLockHooks hooks)
    : _inner(inner), _hooks(hooks)
{
}

bool LvglLockedUiPort::show(NoticeKind kind, std::string_view text)
{
    if (!_hooks.valid()) {
        return false;
    }
    _hooks.lock(_hooks.ctx);
    const bool ok = _inner.show(kind, text);
    _hooks.unlock(_hooks.ctx);
    return ok;
}

void LvglLockedUiPort::clear()
{
    if (!_hooks.valid()) {
        return;
    }
    _hooks.lock(_hooks.ctx);
    _inner.clear();
    _hooks.unlock(_hooks.ctx);
}

NotificationPresenter::NotificationPresenter(ResourceArbiter& arbiter, NotificationUiPort& ui)
    : _arbiter(arbiter), _ui(ui)
{
}

bool NotificationPresenter::textAllowed(std::string_view text) const
{
    return !text.empty() && text.size() <= max_text_bytes && text.find('\0') == std::string_view::npos &&
           jsonSafeText(text);
}

bool NotificationPresenter::present(NoticeKind kind, std::string_view text, Tick now)
{
    if (!textAllowed(text)) {
        return false;
    }
    if (_arbiter.xiaozhiActivity() == ResourceArbiter::XiaozhiActivity::Busy) {
        return false;
    }

    // 新呈現先清舊畫面（不持 lock 做 arbiter）。
    if (_visible) {
        _ui.clear();
        _visible = false;
    }

    const Generation generation = _arbiter.beginPresentation(now);
    if (generation == 0 || !_arbiter.tryAcquire(generation, ResourceArbiter::Resource::Ui, now)) {
        return false;
    }
    if (!_arbiter.mayCommit(generation, ResourceArbiter::Resource::Ui, now)) {
        _arbiter.release(generation, ResourceArbiter::Resource::Ui);
        return false;
    }

    // 僅在提交可見效果時進入 LVGL lock（由 UiPort 實作保證）。
    if (!_ui.show(kind, text)) {
        _arbiter.release(generation, ResourceArbiter::Resource::Ui);
        return false;
    }

    _generation = generation;
    _kind = kind;
    _visible = true;
    return true;
}

void NotificationPresenter::dismiss(Tick now)
{
    if (_visible) {
        _ui.clear();
        _visible = false;
    }
    if (_generation != 0 && _arbiter.mayCommit(_generation, ResourceArbiter::Resource::Ui, now)) {
        _arbiter.release(_generation, ResourceArbiter::Resource::Ui);
    }
}

ResourceArbiter::CancelConfirmation NotificationPresenter::interrupt(Tick now)
{
    const auto confirmation = _arbiter.cancelCurrent(now);
    if (_visible) {
        _ui.clear();
        _visible = false;
    }
    _generation = 0;
    return confirmation;
}

void NotificationPresenter::onXiaozhiActivity(ResourceArbiter::XiaozhiActivity activity, Tick now)
{
    _arbiter.onXiaozhiActivity(activity, now);
    if (activity == ResourceArbiter::XiaozhiActivity::Busy && _visible) {
        // 搶占：授權已讓出後清屏；不得繼續顯示 Agent 通知。
        _ui.clear();
        _visible = false;
    }
}

bool notificationPresenterMayPresent(const ResourceArbiter& arbiter, ResourceArbiter::Generation generation,
                                     ResourceArbiter::Tick now)
{
    return resourceArbiterCommitGate(arbiter, generation, ResourceArbiter::Resource::Ui, now);
}

}  // namespace stackchan::notifications
