/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include "companion_protocol.h"
#include <string>

namespace companion {

/**
 * @brief 本機執行 Pi 白名單指令；須在 LVGL lock 下呼叫 UI 相關操作。
 */
class CompanionExecutor {
public:
    void apply(const Command& cmd);
    void stopAll(std::string_view reason = "stop");
    std::string currentAnimation() const
    {
        return _current_animation;
    }
    std::string currentExpression() const
    {
        return _current_expression;
    }
    std::string subtitle() const
    {
        return _subtitle;
    }
    std::string deviceState() const
    {
        return _device_state;
    }

private:
    void apply_expression(std::string_view name);
    void apply_animation(std::string_view name);
    void apply_motion(float yaw_deg, float pitch_deg, int speed);

    std::string _current_animation = "idle";
    std::string _current_expression = "neutral";
    std::string _subtitle;
    std::string _device_state = "IDLE";
    bool _active             = true;
};

}  // namespace companion
