/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>
#include <smooth_ui_toolkit.hpp>
#include <uitk/short_namespace.hpp>
#include "core/color/color.hpp"
#include <string_view>

namespace stackchan::addon {

/**
 * @brief 左右 Neon LED 控制；支援單色過渡動畫與彩虹流動模式
 */
class NeonLight {
public:
    NeonLight(int ledCount) : _led_count(ledCount)
    {
    }

    void init();
    void update();

    void setColor(uint8_t r, uint8_t g, uint8_t b);
    void setColor(const uitk::color::Rgb_t& rgb);
    void setColor(uint32_t hex);
    void setColor(std::string_view hex);
    void setDuration(float durationSec);

    /**
     * @brief 開關彩虹流動模式；開啟後會覆蓋單色動畫
     */
    void setRainbowEnabled(bool enabled);

    /**
     * @brief 彩虹色相旋轉速度（度／秒），預設 60 → 約 6 秒一圈
     */
    void setRainbowSpeed(float degreesPerSec);

    bool isRainbowEnabled() const
    {
        return _rainbow_enabled;
    }

    int getLedCount() const
    {
        return _led_count;
    }

protected:
    virtual void set_rgb_color_impl(uint8_t index, uint8_t r, uint8_t g, uint8_t b) = 0;
    virtual void refresh_rgb_impl()                                                 = 0;

private:
    void stop_rainbow();
    void update_rainbow();
    static void hsv_to_rgb(float h, float s, float v, uint8_t& r, uint8_t& g, uint8_t& b);

    int _led_count;
    bool _is_inited              = false;
    bool _snap_to_target_on_rest = false;
    uint32_t _last_tick          = 0;
    uitk::color::AnimateRgb_t _color_anim;

    bool _rainbow_enabled    = false;
    float _rainbow_hue       = 0.0f;
    float _rainbow_speed_dps = 60.0f;  // 度／秒
    static constexpr float _k_update_dt_sec = 0.02f;
    static constexpr uint32_t _k_update_interval_ms =
        static_cast<uint32_t>(_k_update_dt_sec * 1000.0f);  // 與 dt 綁定，避免速度偏差
    static constexpr float _k_rainbow_value = 0.66f;  // 約等同既有測試色 168/255，避免過亮
};

/**
 * @brief 左側 6 顆 Neon LED（硬體 index 0–5）
 */
class LeftNeonLight : public NeonLight {
public:
    LeftNeonLight() : NeonLight(6)
    {
    }

private:
    void set_rgb_color_impl(uint8_t index, uint8_t r, uint8_t g, uint8_t b) override;
    void refresh_rgb_impl() override;
};

/**
 * @brief 右側 6 顆 Neon LED（硬體 index 6–11）
 */
class RightNeonLight : public NeonLight {
public:
    RightNeonLight() : NeonLight(6)
    {
    }

private:
    void set_rgb_color_impl(uint8_t index, uint8_t r, uint8_t g, uint8_t b) override;
    void refresh_rgb_impl() override;
};

}  // namespace stackchan::addon
