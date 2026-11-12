/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#include "default.h"
#include <cmath>

using namespace uitk;
using namespace uitk::lvgl_cpp;
using namespace stackchan::avatar;

static const Vector2i _mouth_pos        = Vector2i(0, 42);
static const Vector2i _mouth_min_offset = Vector2i(-16, -16);
static const Vector2i _mouth_max_offset = Vector2i(16, 16);
static const int _mouth_line_width      = 7;
static const int _lobe_steps            = 12;
static constexpr float _pi              = 3.14159265f;

DefaultMouth::DefaultMouth(lv_obj_t* parent, lv_color_t primaryColor, lv_color_t secondaryColor)
{
    // Line 貓嘴僅使用 primary；保留 secondary 參數以對齊眼睛／泡泡建構簽名
    (void)secondaryColor;

    _mouth = std::make_unique<Line>(parent);
    _mouth->setAlign(LV_ALIGN_CENTER);
    _mouth->setBgOpa(LV_OPA_TRANSP);
    _mouth->setBorderWidth(0);
    _mouth->removeFlag(LV_OBJ_FLAG_SCROLLABLE);
    _mouth->setLineColor(primaryColor);
    _mouth->setLineWidth(_mouth_line_width);
    // 參考圖末端偏方，關閉 round cap
    _mouth->setLineRounded(false);

    setPosition(_position);
    setWeight(0);
    setRotation(0);
}

DefaultMouth::~DefaultMouth()
{
    _mouth.reset();
}

void DefaultMouth::_rebuild_mouth_points()
{
    // weight 0：參考圖靜態 ω；weight 越高瓣葉越深，供 SpeakingModifier 開合
    const int lobe_r = map_range(_weight, 0, 100, 22, 20);
    const int depth  = map_range(_weight, 0, 100, 14, 36);

    // 注意：lv_line_set_points 不複製陣列；改動 _mouth_points 後必須再次 setPoints
    _mouth_points.clear();
    _mouth_points.reserve((_lobe_steps + 1) * 2);

    // 兩瓣底部半圓組成 ω（LVGL y 向下，sin>0 為往下凹）
    auto append_lobe = [&](int cx) {
        for (int i = 0; i <= _lobe_steps; ++i) {
            const float t     = static_cast<float>(i) / static_cast<float>(_lobe_steps);
            const float angle = _pi - t * _pi;  // π → 0
            const int x       = cx + static_cast<int>(std::lround(lobe_r * std::cos(angle)));
            const int y       = static_cast<int>(std::lround(depth * std::sin(angle)));
            _mouth_points.push_back({static_cast<lv_value_precise_t>(x), static_cast<lv_value_precise_t>(y)});
        }
    };

    // 左瓣中心 lobe_r、右瓣中心 3*lobe_r → 總寬約 4*lobe_r
    append_lobe(lobe_r);
    const size_t junction = _mouth_points.size();
    append_lobe(3 * lobe_r);
    // 去掉接點重複的中心點
    if (junction > 0 && _mouth_points.size() > junction) {
        _mouth_points.erase(_mouth_points.begin() + static_cast<std::ptrdiff_t>(junction));
    }

    _mouth->setPoints(_mouth_points);

    // 以 LVGL 實際外接矩形中心為旋轉 pivot（與舊版 mouth 行為一致）
    _mouth->setTransformPivot(_mouth->getWidth() / 2, _mouth->getHeight() / 2);
}

void DefaultMouth::setPosition(const Vector2i& position)
{
    Element::setPosition(position);

    auto pos_x = _mouth_pos.x + map_range(_position.x, -100, 100, _mouth_min_offset.x, _mouth_max_offset.x);
    auto pos_y = _mouth_pos.y + map_range(_position.y, -100, 100, _mouth_min_offset.y, _mouth_max_offset.y);

    // ALIGN_CENTER 下 setPos 為相對螢幕中心的偏移，物件會以自身外接矩形置中
    _mouth->setPos(pos_x, pos_y);
}

void DefaultMouth::setWeight(int weight)
{
    Feature::setWeight(weight);
    _rebuild_mouth_points();
    // 重建後 bbox 可能變，需重算置中偏移
    setPosition(_position);
}

void DefaultMouth::setRotation(int rotation)
{
    Element::setRotation(rotation);
    _mouth->setTransformPivot(_mouth->getWidth() / 2, _mouth->getHeight() / 2);
    _mouth->setRotation(rotation);
}

void DefaultMouth::setVisible(bool visible)
{
    Element::setVisible(visible);
    _mouth->setHidden(!visible);
}
