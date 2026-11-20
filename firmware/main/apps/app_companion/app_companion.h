/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include "companion_client.h"
#include "companion_executor.h"
#include <mooncake.h>
#include <smooth_lvgl.hpp>
#include <cstdint>
#include <memory>
#include <string>

/**
 * @brief StackChan Companion App（Phase 1：連線／UI／安全動作）
 *
 * - 連線 Pi WebSocket（hello／heartbeat）
 * - 顯示文字／表情／動畫標籤、限位轉頭
 * - 觸控 STOP；Pi 離線時本機待機
 * - 退出時關閉 socket、停止馬達、釋放 UI；不改 Xiaozhi
 */
class AppCompanion : public mooncake::AppAbility {
public:
    AppCompanion();

    void onCreate() override;
    void onOpen() override;
    void onRunning() override;
    void onClose() override;

private:
    using Container = smooth_ui_toolkit::lvgl_cpp::Container;
    using Label     = smooth_ui_toolkit::lvgl_cpp::Label;
    using Button    = smooth_ui_toolkit::lvgl_cpp::Button;

    std::unique_ptr<Container> _root;
    std::unique_ptr<Label> _title;
    std::unique_ptr<Label> _status;
    std::unique_ptr<Label> _subtitle;
    std::unique_ptr<Label> _activity;
    std::unique_ptr<Button> _stop_button;

    std::unique_ptr<companion::CompanionClient> _client;
    companion::CompanionExecutor _executor;

    uint32_t _status_tick_ms    = 0;
    uint32_t _reconnect_tick_ms = 0;
    uint32_t _opened_at_ms      = 0;
    int _idle_modifier_id       = -1;
    bool _ui_ready              = false;
    bool _avatar_ready          = false;
    companion::LinkState _last_link = companion::LinkState::Idle;

    std::string _pi_ws_url;
    std::string _pi_token;

    void load_settings();
    void create_ui();
    void destroy_ui();
    void setup_avatar();
    void teardown_avatar();
    void start_client();
    void handle_stop_touch();
    void drain_commands();
    void refresh_status_labels();
    void update_offline_idle();
};
