/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <ArduinoJson.hpp>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace companion {

constexpr int kProtocolVersion     = 1;
constexpr size_t kMaxTextChars     = 160;
constexpr size_t kMaxQueueDepth    = 24;
constexpr size_t kMaxMessageBytes  = 2048;

// Companion 保守馬達限位（度）；裝置端二次夾取，不信任雲端任意角度
constexpr float kYawDegMin   = -45.0f;
constexpr float kYawDegMax   = 45.0f;
constexpr float kPitchDegMin = -20.0f;
constexpr float kPitchDegMax = 30.0f;
constexpr int kSpeedMin      = 50;
constexpr int kSpeedMax      = 400;

enum class MsgType {
    Unknown,
    HelloOk,
    Heartbeat,
    Ack,
    TextShow,
    ExpressionSet,
    MotionSet,
    AnimationPlay,
    StateSet,
    PetState,
    Stop,
    Error,
};

struct Command {
    MsgType type           = MsgType::Unknown;
    std::string id;
    std::string text;
    std::string name;
    std::string state;
    std::string session_id;
    float yaw_deg          = 0;
    float pitch_deg        = 0;
    int speed              = 200;
    int duration_ms        = 0;
    bool loop              = false;
    bool partial           = false;
    bool ok                = true;
    std::string error_code;
};

bool IsAllowedAnimation(std::string_view name);
bool IsAllowedExpression(std::string_view name);
MsgType ParseMsgType(std::string_view type);
std::optional<Command> ParseCommand(std::string_view json, std::string* error_code = nullptr);
std::string MakeHelloJson(std::string_view device_id, std::string_view firmware_version);
std::string MakeHeartbeatJson(uint32_t uptime_ms, std::string_view state);
std::string MakeStopJson(std::string_view reason);
std::string MakeDeviceModeJson(std::string_view mode, bool active);
std::string MakeTouchJson(std::string_view zone, std::string_view action);
std::string MakeAckJson(std::string_view reply_to, bool ok);

}  // namespace companion
