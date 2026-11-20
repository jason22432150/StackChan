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
#include <wifi_manager.h>
#include <cstdio>
#include <memory>

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

    // 與原廠 Avatar 相同：先啟動 Wi-Fi／lwIP，再建立 WebSocket。
    // 否則 WebSocket::Connect → getaddrinfo 會觸發 tcpip Invalid mbox assert 並重啟。
    std::unique_ptr<view::LoadingPage> loading_page;
    {
        LvglLockGuard lock;
        loading_page = std::make_unique<view::LoadingPage>(kThemeBorderColor, kThemeColor);
        loading_page->setMessage("Starting\nWi-Fi...");
    }
    GetHAL().startNetwork([&](std::string_view msg) {
        LvglLockGuard lock;
        if (loading_page) {
            loading_page->setMessage(msg);
        }
    });
    {
        LvglLockGuard lock;
        loading_page.reset();
    }

    // 順序必須與原廠 Avatar 一致：先建臉，再建立 home／status，否則全螢幕
    // avatar 會蓋住返回主頁按鈕，導致無法觸發 close()。
    create_ui();
    setup_avatar();
    {
        LvglLockGuard lock;
        raise_overlays();
        view::create_home_indicator([this]() { close(); }, kThemeColor, kThemeBorderColor);
        view::create_status_bar(kThemeColor, kThemeBorderColor);
    }
    start_client();
    _opened_at_ms      = GetHAL().millis();
    _status_tick_ms    = _opened_at_ms;
    _reconnect_tick_ms = _opened_at_ms;
}

void AppCompanion::onRunning()
{
    if (!_ui_ready) {
        return;
    }

    if (_client) {
        _client->tickHeartbeat(GetHAL().millis(), kHeartbeatMs);
    }

    const auto link = _client ? _client->linkState() : LinkState::Idle;

    // 離線重連：不可在 Connect 進行中再次 start（stop/join 會堵死主迴圈 → IDLE0 WDT）
    if (link == LinkState::Offline && GetHAL().millis() - _reconnect_tick_ms > kReconnectMs) {
        _reconnect_tick_ms = GetHAL().millis();
        if (!WifiManager::GetInstance().IsConnected()) {
            mclog::tagWarn(getAppInfo().name, "wifi down, skip ws reconnect");
        } else if (_client && _client->isConnectInFlight()) {
            mclog::tagInfo(getAppInfo().name, "connect in flight, skip retry");
        } else {
            mclog::tagInfo(getAppInfo().name, "retry connect");
            start_client();
        }
    }

    // 與原廠 Avatar 相同：整段 UI／avatar 更新持 LVGL lock，避免無鎖 setPos 拖死 CPU0
    {
        LvglLockGuard lock;
        drain_commands_locked();

        GetStackChan().update();
        view::update_home_indicator();
        view::update_status_bar();

        if (link != _last_link) {
            _last_link = link;
            update_offline_idle_locked();
            refresh_status_labels_locked();
        }

        if (GetHAL().millis() - _status_tick_ms > 1000) {
            _status_tick_ms = GetHAL().millis();
            refresh_status_labels_locked();
        }
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
    // 與 Avatar／Dance 相同：Wi-Fi／WS 啟動後以 warm reboot 回到 Launcher
    // index 對應 main.cpp 未過濾 app 列表（0=AI.AGENT … 6=COMPANION）
    GetHAL().requestWarmReboot(6);
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

    // home／status 改在 setup_avatar() 之後建立，避免被全螢幕臉蓋住
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
    // 掛在 _root 下（非 screen），才能用 raise_overlays 把 STOP／狀態提到臉之上；
    // home indicator 仍建在 screen，並在 avatar 之後建立以保持最上層。
    avatar->init(_root ? _root->get() : lv_screen_active());
    if (auto* panel = avatar->getPanel()) {
        // 不攔截觸控，讓 STOP 與底部上滑手勢可運作
        panel->removeFlag(LV_OBJ_FLAG_CLICKABLE);
    }
    GetStackChan().attachAvatar(std::move(avatar));
    GetStackChan().addModifier(std::make_unique<BreathModifier>());
    GetStackChan().addModifier(std::make_unique<BlinkModifier>());
    _avatar_ready = true;
}

void AppCompanion::raise_overlays()
{
    // 將狀態／STOP 提到臉之上；home indicator 另於呼叫端建立
    if (_title) {
        _title->moveForeground();
    }
    if (_status) {
        _status->moveForeground();
    }
    if (_activity) {
        _activity->moveForeground();
    }
    if (_subtitle) {
        _subtitle->moveForeground();
    }
    if (_stop_button) {
        _stop_button->moveForeground();
    }
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
    }
    const auto device_id = GetHAL().getFactoryMacString();
    // start() 內部會取消舊連線；不可在此同步 join，以免堵住 onRunning
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
        refresh_status_labels_locked();
    }
    if (_client) {
        _client->sendText(MakeStopJson("touch"));
        _client->sendText(MakeTouchJson("screen", "stop"));
    }
}

void AppCompanion::drain_commands_locked()
{
    if (!_client) {
        return;
    }
    Command cmd;
    // 限制單次處理數量，避免一次抽太多阻塞 UI（呼叫端已持 LVGL lock）
    for (int i = 0; i < 8 && _client->popCommand(cmd); ++i) {
        if (cmd.type == MsgType::HelloOk || cmd.type == MsgType::Heartbeat || cmd.type == MsgType::Ack) {
            continue;
        }
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

void AppCompanion::refresh_status_labels_locked()
{
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

void AppCompanion::update_offline_idle_locked()
{
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
