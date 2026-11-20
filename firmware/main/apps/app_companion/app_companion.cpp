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
#include <stackchan/stackchan.h>
#include <settings.h>
#include <cstdio>

using namespace mooncake;
using namespace stackchan;
using namespace companion;

namespace {

constexpr uint32_t kThemeColor       = 0x3DAA8E;
constexpr uint32_t kThemeBorderColor = 0x1B4F44;
constexpr const char* kAppName       = "COMPANION";
constexpr uint32_t kHeartbeatMs      = 5000;
constexpr uint32_t kReconnectMs      = 5000;
constexpr const char* kDefaultWsUrl  = "ws://192.168.1.1:8765/ws/device";

const char* LinkStateLabel(LinkState state)
{
    switch (state) {
        case LinkState::Connecting:
            return "connecting";
        case LinkState::Online:
            return "online";
        case LinkState::Offline:
            return "offline";
        case LinkState::Idle:
        default:
            return "idle";
    }
}

}  // namespace

AppCompanion::AppCompanion()
{
    setAppInfo().name = kAppName;
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
    load_settings();
    create_ui();
    setup_avatar();
    start_client();
    _opened_at_ms       = GetHAL().millis();
    _status_tick_ms     = _opened_at_ms;
    _reconnect_tick_ms  = _opened_at_ms;
}

void AppCompanion::onRunning()
{
    if (!_ui_ready) {
        return;
    }

    // 網路回呼只入隊；此處抽取並在 LVGL lock 下更新，避免阻塞 WS 執行緒
    drain_commands();

    if (_client) {
        _client->tickHeartbeat(GetHAL().millis(), kHeartbeatMs);
    }

    GetStackChan().update();
    view::update_home_indicator();
    view::update_status_bar();

    const auto link = _client ? _client->linkState() : LinkState::Idle;
    if (link != _last_link) {
        _last_link = link;
        update_offline_idle();
        refresh_status_labels();
    }

    // 離線自動重連（不重啟裝置）
    if (link == LinkState::Offline && GetHAL().millis() - _reconnect_tick_ms > kReconnectMs) {
        _reconnect_tick_ms = GetHAL().millis();
        mclog::tagInfo(getAppInfo().name, "retry connect");
        start_client();
    }

    if (GetHAL().millis() - _status_tick_ms > 1000) {
        _status_tick_ms = GetHAL().millis();
        refresh_status_labels();
    }
}

void AppCompanion::onClose()
{
    mclog::tagInfo(getAppInfo().name, "on close");
    // STOP 優先：先停本機動作，再斷線通知 Pi
    _executor.stopAll("app_close");
    if (_client) {
        _client->stop();
        _client.reset();
    }
    teardown_avatar();
    destroy_ui();
}

void AppCompanion::load_settings()
{
    // 一般 NVS，不寫 eFuse；未設定時使用預設 LAN URL
    Settings settings("companion", false);
    _pi_ws_url = settings.GetString("pi_ws_url", kDefaultWsUrl);
    _pi_token  = settings.GetString("pi_token", "");
}

void AppCompanion::create_ui()
{
    LvglLockGuard lock;

    _root = std::make_unique<Container>(lv_screen_active());
    _root->setSize(lv_pct(100), lv_pct(100));
    _root->setBgColor(lv_color_hex(0x102A26));
    _root->setBorderWidth(0);
    _root->setRadius(0);
    _root->removeFlag(LV_OBJ_FLAG_SCROLLABLE);

    _title = std::make_unique<Label>(_root->get());
    _title->setText("StackChan Companion");
    _title->setTextColor(lv_color_hex(0xE8FFF7));
    _title->align(LV_ALIGN_TOP_MID, 0, 28);

    _status = std::make_unique<Label>(_root->get());
    _status->setText("starting...");
    _status->setTextColor(lv_color_hex(0xA6D9CB));
    _status->setTextAlign(LV_TEXT_ALIGN_CENTER);
    _status->align(LV_ALIGN_TOP_MID, 0, 56);

    _activity = std::make_unique<Label>(_root->get());
    _activity->setText("anim: idle");
    _activity->setTextColor(lv_color_hex(0x7FCFB8));
    _activity->setTextAlign(LV_TEXT_ALIGN_CENTER);
    _activity->align(LV_ALIGN_BOTTOM_MID, 0, -72);

    _subtitle = std::make_unique<Label>(_root->get());
    _subtitle->setText("");
    _subtitle->setWidth(280);
    _subtitle->setTextColor(lv_color_hex(0xD7FFF2));
    _subtitle->setTextAlign(LV_TEXT_ALIGN_CENTER);
    _subtitle->align(LV_ALIGN_BOTTOM_MID, 0, -48);

    _stop_button = std::make_unique<Button>(_root->get());
    _stop_button->setSize(120, 40);
    _stop_button->align(LV_ALIGN_BOTTOM_MID, 0, -8);
    _stop_button->label().setText("STOP");
    _stop_button->onClick().connect([this]() { handle_stop_touch(); });

    view::create_home_indicator([this]() { close(); }, kThemeColor, kThemeBorderColor);
    view::create_status_bar(kThemeColor, kThemeBorderColor);

    _ui_ready = true;
}

void AppCompanion::destroy_ui()
{
    LvglLockGuard lock;
    view::destroy_home_indicator();
    view::destroy_status_bar();
    _stop_button.reset();
    _subtitle.reset();
    _activity.reset();
    _status.reset();
    _title.reset();
    _root.reset();
    _ui_ready = false;
}

void AppCompanion::setup_avatar()
{
    LvglLockGuard lock;
    auto avatar = std::make_unique<avatar::DefaultAvatar>();
    // 放在畫面中央偏上，避免擋住 STOP／狀態文字
    avatar->init(lv_screen_active());
    GetStackChan().attachAvatar(std::move(avatar));
    GetStackChan().addModifier(std::make_unique<BreathModifier>());
    GetStackChan().addModifier(std::make_unique<BlinkModifier>());
    _avatar_ready = true;
}

void AppCompanion::teardown_avatar()
{
    LvglLockGuard lock;
    if (_idle_modifier_id >= 0) {
        GetStackChan().removeModifier(_idle_modifier_id);
        _idle_modifier_id = -1;
    }
    GetStackChan().clearModifiers();
    GetStackChan().resetAvatar();
    GetStackChan().motion().stop();
    GetStackChan().motion().goHome(200);
    _avatar_ready = false;
}

void AppCompanion::start_client()
{
    if (!_client) {
        _client = std::make_unique<CompanionClient>();
    } else {
        _client->stop();
    }
    const auto device_id = GetHAL().getFactoryMacString();
    _client->start(_pi_ws_url, _pi_token, device_id);
    _last_link = _client->linkState();
}

void AppCompanion::handle_stop_touch()
{
    // 觸控 STOP：先停本機，再通知 Pi（即使離線也必須能停）
    {
        LvglLockGuard lock;
        _executor.stopAll("touch");
        if (_subtitle) {
            _subtitle->setText("");
        }
    }
    if (_client) {
        _client->sendText(MakeStopJson("touch"));
        _client->sendText(MakeTouchJson("screen", "stop"));
    }
    refresh_status_labels();
}

void AppCompanion::drain_commands()
{
    if (!_client) {
        return;
    }
    Command cmd;
    // 限制單次處理數量，避免一次抽太多阻塞 UI
    for (int i = 0; i < 8 && _client->popCommand(cmd); ++i) {
        if (cmd.type == MsgType::HelloOk || cmd.type == MsgType::Heartbeat || cmd.type == MsgType::Ack) {
            continue;
        }
        LvglLockGuard lock;
        _executor.apply(cmd);
        if (_subtitle && !_executor.subtitle().empty()) {
            _subtitle->setText(_executor.subtitle().c_str());
        }
        if (_activity) {
            auto line = std::string("anim: ") + _executor.currentAnimation() + " / " + _executor.currentExpression();
            _activity->setText(line.c_str());
        }
    }
}

void AppCompanion::refresh_status_labels()
{
    LvglLockGuard lock;
    if (!_status) {
        return;
    }
    const auto link = _client ? _client->linkState() : LinkState::Idle;
    char buf[160];
    std::snprintf(buf, sizeof(buf), "Pi: %s\nstate: %s\nmissed hb: %u", LinkStateLabel(link),
                  _executor.deviceState().c_str(),
                  _client ? static_cast<unsigned>(_client->missedHeartbeats()) : 0u);
    _status->setText(buf);
}

void AppCompanion::update_offline_idle()
{
    LvglLockGuard lock;
    if (_last_link == LinkState::Offline || _last_link == LinkState::Connecting) {
        if (_idle_modifier_id < 0 && _avatar_ready) {
            _idle_modifier_id = GetStackChan().addModifier(std::make_unique<IdleMotionModifier>(6000, 12000));
        }
    } else if (_last_link == LinkState::Online) {
        if (_idle_modifier_id >= 0) {
            GetStackChan().removeModifier(_idle_modifier_id);
            _idle_modifier_id = -1;
        }
    }
}
