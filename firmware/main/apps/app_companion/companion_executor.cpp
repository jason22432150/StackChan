/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#include "companion_executor.h"
#include <stackchan/stackchan.h>
#include <mooncake_log.h>

using namespace stackchan;
using namespace stackchan::avatar;

namespace companion {
namespace {
constexpr std::string_view kTag = "CompanionExec";

Emotion ToEmotion(std::string_view name)
{
    if (name == "happy" || name == "curious" || name == "calm") return Emotion::Happy;
    if (name == "angry") return Emotion::Angry;
    if (name == "sad") return Emotion::Sad;
    if (name == "doubt" || name == "thinking") return Emotion::Doubt;
    if (name == "sleepy") return Emotion::Sleepy;
    return Emotion::Neutral;
}
}  // namespace

void CompanionExecutor::apply(const Command& cmd)
{
    if (!_active && cmd.type != MsgType::Stop) {
        return;
    }

    switch (cmd.type) {
        case MsgType::TextShow:
            _subtitle = cmd.text;
            if (GetStackChan().hasAvatar()) {
                GetStackChan().avatar().setSpeech(cmd.text);
            }
            break;
        case MsgType::ExpressionSet:
            apply_expression(cmd.name);
            break;
        case MsgType::AnimationPlay:
            apply_animation(cmd.name);
            break;
        case MsgType::MotionSet:
            apply_motion(cmd.yaw_deg, cmd.pitch_deg, cmd.speed);
            break;
        case MsgType::StateSet:
            _device_state = cmd.state;
            break;
        case MsgType::PetState:
            if (!cmd.name.empty()) {
                apply_animation(cmd.name);
            }
            break;
        case MsgType::Stop:
            stopAll("remote_stop");
            break;
        default:
            break;
    }
}

void CompanionExecutor::stopAll(std::string_view reason)
{
    mclog::tagInfo(kTag, "stopAll: {}", reason);
    if (GetStackChan().hasAvatar()) {
        GetStackChan().avatar().clearSpeech();
        GetStackChan().avatar().setEmotion(Emotion::Neutral);
    }
    auto& motion = GetStackChan().motion();
    motion.stop();
    motion.goHome(200);
    _subtitle.clear();
    _current_expression = "neutral";
    _current_animation  = "idle";
    _device_state       = "IDLE";
}

void CompanionExecutor::apply_expression(std::string_view name)
{
    _current_expression = std::string(name);
    if (GetStackChan().hasAvatar()) {
        GetStackChan().avatar().setEmotion(ToEmotion(name));
    }
}

void CompanionExecutor::apply_animation(std::string_view name)
{
    if (!IsAllowedAnimation(name)) {
        mclog::tagWarn(kTag, "reject animation {}", name);
        return;
    }
    _current_animation = std::string(name);
    // Phase 1：以表情＋簡短字幕表達活動；完整素材動畫留後續 Phase
    if (name == "sleep") {
        apply_expression("sleepy");
    } else if (name == "read" || name == "work" || name == "explore" || name == "create") {
        apply_expression("curious");
    } else if (name == "eat" || name == "celebrate") {
        apply_expression("happy");
    } else if (name == "walk" || name == "look_around") {
        apply_expression("neutral");
        apply_motion(15.0f, 0.0f, 180);
    } else {
        apply_expression("neutral");
    }
    if (GetStackChan().hasAvatar()) {
        GetStackChan().avatar().setSpeech(_current_animation);
    }
}

void CompanionExecutor::apply_motion(float yaw_deg, float pitch_deg, int speed)
{
    // 協定為度；StackChan motion API 使用 0.1 度單位
    const int yaw   = static_cast<int>(yaw_deg * 10.0f);
    const int pitch = static_cast<int>(pitch_deg * 10.0f);
    auto& motion    = GetStackChan().motion();
    if (motion.isModifyLocked()) {
        mclog::tagWarn(kTag, "motion locked, skip");
        return;
    }
    // 若上一動作尚未完成，不堆疊新指令（與 idle_motion 相同策略）
    if (motion.isMoving()) {
        mclog::tagInfo(kTag, "motion busy, skip new command");
        return;
    }
    motion.setAutoAngleSyncEnabled(false);
    motion.moveWithSpeed(yaw, pitch, speed);
}

}  // namespace companion
