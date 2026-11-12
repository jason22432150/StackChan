/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include "../../avatar/avatar.h"
#include "../../avatar/elements/feature.h"
#include <lvgl.h>
#include <smooth_lvgl.hpp>
#include <memory>
#include <vector>

namespace stackchan::avatar {

/**
 * @brief
 *
 */
class DefaultAvatar : public Avatar {
public:
    // 參考風格：黑底 + 金黃五官（約 #FFBF40）
    lv_color_t primaryColor   = lv_color_hex(0xFFBF40);
    lv_color_t secondaryColor = lv_color_black();

    void init(lv_obj_t* parent, const lv_font_t* font = &lv_font_montserrat_16);
    uitk::lvgl_cpp::Container* getPanel() const;

private:
    std::unique_ptr<uitk::lvgl_cpp::Container> _pannel;
};

/**
 * @brief
 *
 */
class DefaultEyes : public Feature {
public:
    DefaultEyes(lv_obj_t* parent, lv_color_t primaryColor, lv_color_t secondaryColor, bool isLeftEye);
    ~DefaultEyes();

    void setPosition(const uitk::Vector2i& position) override;
    void setWeight(int weight) override;
    void setRotation(int rotation) override;
    void setEmotion(const Emotion& emotion) override;
    void setVisible(bool visible) override;
    void setSize(int size) override;

private:
    bool _is_left_eye    = false;
    int _eyelid_offset_y = 0;

    std::unique_ptr<uitk::lvgl_cpp::Container> _container;
    std::unique_ptr<uitk::lvgl_cpp::Container> _eye;
    std::unique_ptr<uitk::lvgl_cpp::Container> _eyelid;
};

/**
 * @brief
 *
 */
class DefaultMouth : public Feature {
public:
    DefaultMouth(lv_obj_t* parent, lv_color_t primaryColor, lv_color_t secondaryColor);
    ~DefaultMouth();

    void setPosition(const uitk::Vector2i& position) override;
    void setWeight(int weight) override;
    void setRotation(int rotation) override;
    void setVisible(bool visible) override;

private:
    /** 依 weight 重建 ω／貓嘴折線（points 需持續存活供 lv_line 使用） */
    void _rebuild_mouth_points();

    std::unique_ptr<uitk::lvgl_cpp::Line> _mouth;
    std::vector<lv_point_precise_t> _mouth_points;
};

/**
 * @brief
 *
 */
class DefaultSpeechBubble : public SpeechBubble {
public:
    DefaultSpeechBubble(lv_obj_t* parent, lv_color_t primaryColor, lv_color_t secondaryColor, const lv_font_t* font);
    ~DefaultSpeechBubble();

    void setSpeech(std::string_view text) override;
    void clearSpeech() override;
    void setVisible(bool visible) override;
    void setTextFont(void* font) override;

private:
    std::unique_ptr<uitk::lvgl_cpp::Container> _container;
    std::unique_ptr<uitk::lvgl_cpp::Image> _arrow;
    std::unique_ptr<uitk::lvgl_cpp::Container> _bubble;
    std::unique_ptr<uitk::lvgl_cpp::Label> _text;
};

}  // namespace stackchan::avatar
