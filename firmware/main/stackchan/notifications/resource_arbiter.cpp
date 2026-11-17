#include "resource_arbiter.h"

namespace stackchan::notifications {

void ResourceArbiter::noteTick(Tick now)
{
    // 單調時鐘倒退視為安全事件：立即失效目前 Generation。
    if (now < _last_tick) {
        clearLease(Resource::Ui);
        clearLease(Resource::Audio);
        clearLease(Resource::Motion);
        _ui_yielded = true;
        if (_generation != 0) {
            ++_generation;
        }
    }
    _last_tick = now;
}

void ResourceArbiter::clearLease(Resource resource)
{
    switch (resource) {
        case Resource::Ui:
            _lease_ui = false;
            break;
        case Resource::Audio:
            _lease_audio = false;
            break;
        case Resource::Motion:
            _lease_motion = false;
            break;
    }
}

bool ResourceArbiter::hasLease(Resource resource) const
{
    switch (resource) {
        case Resource::Ui:
            return _lease_ui;
        case Resource::Audio:
            return _lease_audio;
        case Resource::Motion:
            return _lease_motion;
    }
    return false;
}

ResourceArbiter::Generation ResourceArbiter::beginPresentation(Tick now)
{
    noteTick(now);
    // 新呈現必定取得新 Generation，使上一輪延遲 callback 全部失效。
    ++_generation;
    if (_generation == 0) {
        ++_generation;
    }
    _lease_ui = false;
    _lease_audio = false;
    _lease_motion = false;
    _ui_yielded = (_xiaozhi == XiaozhiActivity::Busy);
    return _generation;
}

bool ResourceArbiter::tryAcquire(Generation generation, Resource resource, Tick now)
{
    noteTick(now);
    if (generation == 0 || generation != _generation) {
        return false;
    }
    if (_xiaozhi == XiaozhiActivity::Busy) {
        // Busy：Audio／Motion 禁止；UI 讓出不得新取租約。
        return false;
    }
    if (_ui_yielded && resource == Resource::Ui) {
        return false;
    }
    switch (resource) {
        case Resource::Ui:
            _lease_ui = true;
            _ui_yielded = false;
            return true;
        case Resource::Audio:
            _lease_audio = true;
            return true;
        case Resource::Motion:
            _lease_motion = true;
            return true;
    }
    return false;
}

void ResourceArbiter::release(Generation generation, Resource resource)
{
    if (generation == 0 || generation != _generation) {
        return;
    }
    clearLease(resource);
}

bool ResourceArbiter::mayCommit(Generation generation, Resource resource, Tick now) const
{
    if (now < _last_tick) {
        return false;
    }
    if (generation == 0 || generation != _generation) {
        return false;
    }
    if (_xiaozhi == XiaozhiActivity::Busy) {
        return false;
    }
    if (resource == Resource::Ui && _ui_yielded) {
        return false;
    }
    return hasLease(resource);
}

ResourceArbiter::CancelConfirmation ResourceArbiter::cancelCurrent(Tick now)
{
    noteTick(now);
    CancelConfirmation confirmation;
    confirmation.invalidated_generation = _generation;
    confirmation.had_ui = _lease_ui;
    confirmation.had_audio = _lease_audio;
    confirmation.had_motion = _lease_motion;

    clearLease(Resource::Ui);
    clearLease(Resource::Audio);
    clearLease(Resource::Motion);

    if (_generation != 0) {
        ++_generation;
        if (_generation == 0) {
            ++_generation;
        }
        confirmation.generation_bumped = true;
        // 新 Generation 從乾淨狀態開始；下一輪呈現仍應呼叫 beginPresentation。
        _ui_yielded = false;
    } else {
        _ui_yielded = true;
    }
    return confirmation;
}

ResourceArbiter::CancelConfirmation ResourceArbiter::revokeAll(Tick now)
{
    return cancelCurrent(now);
}

void ResourceArbiter::onXiaozhiActivity(XiaozhiActivity activity, Tick now)
{
    noteTick(now);
    _xiaozhi = activity;
    if (activity == XiaozhiActivity::Busy) {
        // 搶占：先同步撤銷通知音訊／動作租約並讓出 UI，不 bump Generation，
        // 以便對話結束後由上層重評估後再 tryAcquire。
        clearLease(Resource::Audio);
        clearLease(Resource::Motion);
        _ui_yielded = true;
        // UI 租約也清除，避免 Busy 期間殘留 hasLease(Ui)==true 的誤解。
        clearLease(Resource::Ui);
    } else {
        // Idle：允許同一 Generation 重新取租約（TTL／政策重評估由上層負責）。
        _ui_yielded = false;
    }
}

bool resourceArbiterCommitGate(const ResourceArbiter& arbiter, ResourceArbiter::Generation generation,
                               ResourceArbiter::Resource resource, ResourceArbiter::Tick now)
{
    return arbiter.mayCommit(generation, resource, now);
}

}  // namespace stackchan::notifications
