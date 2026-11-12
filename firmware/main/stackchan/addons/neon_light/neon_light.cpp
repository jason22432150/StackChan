/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#include "neon_light.h"
#include <hal/hal.h>
#include <cmath>

using namespace stackchan::addon;

void NeonLight::init()
{
    // Setup color animation
    _color_anim.duration = 0.3f;
    _color_anim.begin();

    _is_inited = true;
}

void NeonLight::hsv_to_rgb(float h, float s, float v, uint8_t& r, uint8_t& g, uint8_t& b)
{
    // 標準 HSV→RGB；h 單位為度，範圍會先正規化到 [0, 360)
    while (h < 0.0f) {
        h += 360.0f;
    }
    while (h >= 360.0f) {
        h -= 360.0f;
    }

    const float c = v * s;
    const float x = c * (1.0f - fabsf(fmodf(h / 60.0f, 2.0f) - 1.0f));
    const float m = v - c;

    float rp = 0.0f;
    float gp = 0.0f;
    float bp = 0.0f;
    if (h < 60.0f) {
        rp = c;
        gp = x;
    } else if (h < 120.0f) {
        rp = x;
        gp = c;
    } else if (h < 180.0f) {
        gp = c;
        bp = x;
    } else if (h < 240.0f) {
        gp = x;
        bp = c;
    } else if (h < 300.0f) {
        rp = x;
        bp = c;
    } else {
        rp = c;
        bp = x;
    }

    r = static_cast<uint8_t>((rp + m) * 255.0f + 0.5f);
    g = static_cast<uint8_t>((gp + m) * 255.0f + 0.5f);
    b = static_cast<uint8_t>((bp + m) * 255.0f + 0.5f);
}

void NeonLight::update_rainbow()
{
    _rainbow_hue += _rainbow_speed_dps * _k_update_dt_sec;
    while (_rainbow_hue >= 360.0f) {
        _rainbow_hue -= 360.0f;
    }
    while (_rainbow_hue < 0.0f) {
        _rainbow_hue += 360.0f;
    }

    // 各 LED 色相錯開，形成沿燈條流動的彩虹
    const float hue_step = (_led_count > 0) ? (360.0f / static_cast<float>(_led_count)) : 0.0f;
    for (int i = 0; i < _led_count; i++) {
        uint8_t r = 0;
        uint8_t g = 0;
        uint8_t b = 0;
        hsv_to_rgb(_rainbow_hue + static_cast<float>(i) * hue_step, 1.0f, _k_rainbow_value, r, g, b);
        set_rgb_color_impl(static_cast<uint8_t>(i), r, g, b);
    }
    refresh_rgb_impl();
}

void NeonLight::update()
{
    if (!_is_inited) {
        init();
    }

    // Keep update in at most 50Hz
    if (GetHAL().millis() - _last_tick < _k_update_interval_ms) {
        return;
    }
    _last_tick = GetHAL().millis();

    if (_rainbow_enabled) {
        update_rainbow();
        return;
    }

    // Apply color animation
    if (!_color_anim.done()) {
        _color_anim.updateWithDelta(_k_update_dt_sec);  // Fixed delta time for consistency
        for (int i = 0; i < _led_count; i++) {
            set_rgb_color_impl(static_cast<uint8_t>(i), _color_anim.r, _color_anim.g, _color_anim.b);
        }
        refresh_rgb_impl();
    }

    // Snap to target color when animation ends
    else if (_snap_to_target_on_rest) {
        _snap_to_target_on_rest = false;
        for (int i = 0; i < _led_count; i++) {
            set_rgb_color_impl(static_cast<uint8_t>(i), _color_anim.r, _color_anim.g, _color_anim.b);
        }
        refresh_rgb_impl();
    }
}

void NeonLight::stop_rainbow()
{
    _rainbow_enabled = false;
}

void NeonLight::setRainbowEnabled(bool enabled)
{
    _rainbow_enabled = enabled;
    if (enabled) {
        // 進入彩虹時略過單色 snap，避免最後一幀覆蓋彩虹
        _snap_to_target_on_rest = false;
    }
}

void NeonLight::setRainbowSpeed(float degreesPerSec)
{
    _rainbow_speed_dps = degreesPerSec;
}

void NeonLight::setColor(uint8_t r, uint8_t g, uint8_t b)
{
    stop_rainbow();
    _color_anim.move(r, g, b);
    _snap_to_target_on_rest = true;
}

void NeonLight::setColor(const uitk::color::Rgb_t& rgb)
{
    stop_rainbow();
    _color_anim.move(rgb);
    _snap_to_target_on_rest = true;
}

void NeonLight::setColor(uint32_t hex)
{
    stop_rainbow();
    _color_anim.move(hex);
    _snap_to_target_on_rest = true;
}

void NeonLight::setColor(std::string_view hex)
{
    if (hex.empty()) {
        return;
    }
    stop_rainbow();
    _color_anim.move(hex);
    _snap_to_target_on_rest = true;
}

void NeonLight::setDuration(float durationSec)
{
    _color_anim.duration = durationSec;
    _color_anim.begin();
}

void LeftNeonLight::set_rgb_color_impl(uint8_t index, uint8_t r, uint8_t g, uint8_t b)
{
    GetHAL().setRgbColor(index, r, g, b);
}

void LeftNeonLight::refresh_rgb_impl()
{
    GetHAL().refreshRgb();
}

void RightNeonLight::set_rgb_color_impl(uint8_t index, uint8_t r, uint8_t g, uint8_t b)
{
    GetHAL().setRgbColor(index + 6, r, g, b);
}

void RightNeonLight::refresh_rgb_impl()
{
    GetHAL().refreshRgb();
}
