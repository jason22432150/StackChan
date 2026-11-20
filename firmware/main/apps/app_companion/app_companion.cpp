/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#include "app_companion.h"
#include <hal/hal.h>
#include <mooncake.h>
#include <mooncake_log.h>
#include <assets/assets.h>
#include <apps/common/common.h>

using namespace mooncake;

namespace {

constexpr uint32_t kThemeColor       = 0x3DAA8E;
constexpr uint32_t kThemeBorderColor = 0x1B4F44;
constexpr const char* kAppName       = "COMPANION";

}  // namespace

AppCompanion::AppCompanion()
{
    setAppInfo().name = kAppName;
    // Phase 0 暫用既有 icon；正式圖示可於後續 Phase 新增，不影響功能
    static auto icon            = assets::get_image("icon_bell.bin");
    setAppInfo().icon           = (void*)&icon;
    static uint32_t theme_color = kThemeColor;
    setAppInfo().userData       = (void*)&theme_color;
}

void AppCompanion::onCreate()
{
    mclog::tagInfo(getAppInfo().name, "on create");
}

void AppCompanion::onOpen()
{
    mclog::tagInfo(getAppInfo().name, "on open");
    create_ui();
    _status_tick_ms = GetHAL().millis();
}

void AppCompanion::onRunning()
{
    if (!_ui_ready) {
        return;
    }

    // 低頻狀態刷新；Phase 0 不做網路或雲端呼叫，避免阻塞 Mooncake 迴圈
    view::update_home_indicator();
    view::update_status_bar();

    if (GetHAL().millis() - _status_tick_ms < 1000) {
        return;
    }
    _status_tick_ms = GetHAL().millis();

    LvglLockGuard lock;
    if (_status) {
        _status->setText("Phase 0 shell\nPi: not connected\nTouch home to exit");
    }
}

void AppCompanion::onClose()
{
    mclog::tagInfo(getAppInfo().name, "on close");
    // 立即釋放 UI；Phase 0 尚未取得麥克風／喇叭／socket，故無需額外停音或斷線
    destroy_ui();
}

void AppCompanion::create_ui()
{
    LvglLockGuard lock;

    _root = std::make_unique<Container>(lv_screen_active());
    _root->setSize(lv_pct(100), lv_pct(100));
    _root->setBgColor(lv_color_hex(0x102A26));
    _root->setBorderWidth(0);
    _root->setRadius(0);

    _title = std::make_unique<Label>(_root->get());
    _title->setText("StackChan Companion");
    _title->setTextColor(lv_color_hex(0xE8FFF7));
    _title->align(LV_ALIGN_TOP_MID, 0, 28);

    _status = std::make_unique<Label>(_root->get());
    _status->setText("Phase 0 shell\nPi: not connected\nTouch home to exit");
    _status->setTextColor(lv_color_hex(0xA6D9CB));
    _status->setTextAlign(LV_TEXT_ALIGN_CENTER);
    _status->align(LV_ALIGN_CENTER, 0, 8);

    // 與既有 App 相同的返回／狀態列；退出時 destroy_ui 會清掉
    view::create_home_indicator([this]() { close(); }, kThemeColor, kThemeBorderColor);
    view::create_status_bar(kThemeColor, kThemeBorderColor);

    _ui_ready = true;
}

void AppCompanion::destroy_ui()
{
    LvglLockGuard lock;

    view::destroy_home_indicator();
    view::destroy_status_bar();

    _status.reset();
    _title.reset();
    _root.reset();
    _ui_ready = false;
}
