/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#include "default.h"

using namespace uitk;
using namespace uitk::lvgl_cpp;
using namespace stackchan::avatar;

// 直橢圓眼：約 1:2 寬高比，對齊參考圖的垂直橢圓
static const Vector2i _eye_pos          = Vector2i(-52, -28);
static const Vector2i _eye_min_offset   = Vector2i(-16, -16);
static const Vector2i _eye_max_offset   = Vector2i(16, 16);
static const Vector2i _eye_width_limit  = Vector2i(14, 30);  // size -100..100 → 寬
static const Vector2i _eye_height_limit = Vector2i(28, 60);  // size -100..100 → 高（約 2× 寬）

DefaultEyes::DefaultEyes(lv_obj_t* parent, lv_color_t primaryColor, lv_color_t secondaryColor, bool isLeftEye)
{
    _is_left_eye = isLeftEye;

    const int container_size = _eye_height_limit.y;

    _container = std::make_unique<Container>(parent);
    _container->setRadius(0);
    _container->setAlign(LV_ALIGN_CENTER);
    _container->setBorderWidth(0);
    _container->setBgOpa(0);
    _container->removeFlag(LV_OBJ_FLAG_SCROLLABLE);
    _container->setPadding(0, 0, 0, 0);
    _container->setTransformPivot(container_size / 2, container_size / 2);
    _container->setSize(container_size, container_size);

    _eye = std::make_unique<Container>(_container->get());
    // 非正方形 + CIRCLE radius → 橢圓
    _eye->setRadius(LV_RADIUS_CIRCLE);
    _eye->align(LV_ALIGN_CENTER, 0, 0);
    _eye->setBorderWidth(0);
    _eye->setBgColor(primaryColor);
    _eye->removeFlag(LV_OBJ_FLAG_SCROLLABLE);

    _eyelid = std::make_unique<Container>(_container->get());
    // 與眼睛同為橢圓遮罩，半開眼時邊緣較自然
    _eyelid->setRadius(LV_RADIUS_CIRCLE);
    _eyelid->align(LV_ALIGN_CENTER, 0, 0);
    _eyelid->setBorderWidth(0);
    _eyelid->setBgColor(secondaryColor);
    _eyelid->removeFlag(LV_OBJ_FLAG_SCROLLABLE);

    setSize(0);
    setWeight(100);
    setPosition(_position);
    setRotation(0);
}

DefaultEyes::~DefaultEyes()
{
    _eyelid.reset();
    _eye.reset();
    _container.reset();
}

void DefaultEyes::setPosition(const Vector2i& position)
{
    Element::setPosition(position);

    auto pos_x = _is_left_eye ? _eye_pos.x : -_eye_pos.x;
    pos_x += map_range(_position.x, -100, 100, _eye_min_offset.x, _eye_max_offset.x);
    auto pos_y = _eye_pos.y + map_range(_position.y, -100, 100, _eye_min_offset.y, _eye_max_offset.y);

    _container->setPos(pos_x, pos_y);
    _eyelid->setY(_eyelid_offset_y);
}

void DefaultEyes::setWeight(int weight)
{
    Feature::setWeight(weight);

    _eyelid_offset_y = -map_range(_weight, 0, 100, 0, (int)_eyelid->getHeight());

    _eyelid->setY(_eyelid_offset_y);
}

void DefaultEyes::setRotation(int rotation)
{
    Element::setRotation(rotation);

    _container->setRotation(rotation);
}

void DefaultEyes::setEmotion(const Emotion& emotion)
{
    if (getIgnoreEmotion()) {
        return;
    }

    // 還原直橢圓外觀（Happy 會暫時壓扁，離開時需恢復）
    auto restore_eye_geometry = [this]() {
        int eye_w = map_range(_size, -100, 100, _eye_width_limit.x, _eye_width_limit.y);
        int eye_h = map_range(_size, -100, 100, _eye_height_limit.x, _eye_height_limit.y);
        _eye->setSize(eye_w, eye_h);
        _eyelid->setSize(eye_w, eye_h);
    };

    auto apply_style = [this](int weight, int rotation) {
        setWeight(weight);
        if (_is_left_eye) {
            setRotation(rotation);
        } else {
            setRotation(-rotation);
        }
    };

    switch (emotion) {
        case Emotion::Neutral:
            restore_eye_geometry();
            apply_style(100, 0);
            break;
        case Emotion::Happy: {
            // 直橢圓不適合舊版大角度旋轉；改壓成橫向微笑眼 + 輕瞇 + 微外揚
            int eye_w = map_range(_size, -100, 100, _eye_width_limit.x, _eye_width_limit.y);
            int eye_h = map_range(_size, -100, 100, _eye_height_limit.x, _eye_height_limit.y);
            const int smile_w = eye_w + 6;
            const int smile_h = max(10, eye_h / 3);
            _eye->setSize(smile_w, smile_h);
            _eyelid->setSize(smile_w, smile_h);
            apply_style(52, 220);
            break;
        }
        case Emotion::Angry:
            restore_eye_geometry();
            apply_style(70, 350);
            break;
        case Emotion::Sad:
            restore_eye_geometry();
            apply_style(70, -300);
            break;
        case Emotion::Doubt:
            restore_eye_geometry();
            apply_style(75, 0);
            break;
        case Emotion::Sleepy:
            restore_eye_geometry();
            apply_style(35, -50);
            break;
        default:
            break;
    }
}

void DefaultEyes::setVisible(bool visible)
{
    Element::setVisible(visible);

    _container->setHidden(!visible);
}

void DefaultEyes::setSize(int size)
{
    Feature::setSize(size);

    // 維持約 1:2 直橢圓，size 同步縮放寬高
    int eye_w = map_range(_size, -100, 100, _eye_width_limit.x, _eye_width_limit.y);
    int eye_h = map_range(_size, -100, 100, _eye_height_limit.x, _eye_height_limit.y);

    _eye->setSize(eye_w, eye_h);
    _eyelid->setSize(eye_w, eye_h);

    // Force eyelid update
    setWeight(getWeight());
}
