/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <mooncake.h>
#include <smooth_lvgl.hpp>
#include <cstdint>
#include <memory>

/**
 * @brief StackChan Companion App（Phase 0 空殼）
 *
 * 獨立 Mooncake App：可從 Launcher 開啟／退出。
 * Phase 0 不連線 Pi、不占用音訊 Codec、不控制馬達。
 * 原廠 AppAiAgent / Xiaozhi 路徑維持不變。
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

    std::unique_ptr<Container> _root;
    std::unique_ptr<Label> _title;
    std::unique_ptr<Label> _status;
    uint32_t _status_tick_ms = 0;
    bool _ui_ready           = false;

    void create_ui();
    void destroy_ui();
};
