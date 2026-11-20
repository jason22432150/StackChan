/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#include "companion_protocol.h"
#include <algorithm>
#include <cstdio>

namespace companion {
namespace {

bool InList(std::string_view name, const char* const* list, size_t count)
{
    for (size_t i = 0; i < count; ++i) {
        if (name == list[i]) {
            return true;
        }
    }
    return false;
}

float ClampFloat(float value, float lo, float hi)
{
    return std::max(lo, std::min(hi, value));
}

int ClampInt(int value, int lo, int hi)
{
    return std::max(lo, std::min(hi, value));
}

}  // namespace

bool IsAllowedAnimation(std::string_view name)
{
    static const char* kList[] = {"idle",     "sleep", "read",     "reading", "work",
                                  "eat",      "walk",  "look_around", "celebrate", "explore", "create"};
    return InList(name, kList, sizeof(kList) / sizeof(kList[0]));
}

bool IsAllowedExpression(std::string_view name)
{
    static const char* kList[] = {"neutral", "happy", "angry", "sad", "doubt",
                                  "sleepy",  "curious", "calm", "thinking"};
    return InList(name, kList, sizeof(kList) / sizeof(kList[0]));
}

MsgType ParseMsgType(std::string_view type)
{
    if (type == "hello.ok") return MsgType::HelloOk;
    if (type == "heartbeat") return MsgType::Heartbeat;
    if (type == "ack") return MsgType::Ack;
    if (type == "text.show") return MsgType::TextShow;
    if (type == "expression.set") return MsgType::ExpressionSet;
    if (type == "motion.set") return MsgType::MotionSet;
    if (type == "animation.play") return MsgType::AnimationPlay;
    if (type == "state.set") return MsgType::StateSet;
    if (type == "pet.state") return MsgType::PetState;
    if (type == "stop") return MsgType::Stop;
    return MsgType::Unknown;
}

std::optional<Command> ParseCommand(std::string_view json, std::string* error_code)
{
    if (json.size() > kMaxMessageBytes) {
        if (error_code) *error_code = "too_large";
        return std::nullopt;
    }

    ArduinoJson::JsonDocument doc;
    auto err = ArduinoJson::deserializeJson(doc, json);
    if (err) {
        if (error_code) *error_code = "invalid_json";
        return std::nullopt;
    }
    if (!doc["v"].is<int>() || doc["v"].as<int>() != kProtocolVersion) {
        if (error_code) *error_code = "bad_version";
        return std::nullopt;
    }
    if (!doc["id"].is<const char*>() || !doc["type"].is<const char*>()) {
        if (error_code) *error_code = "bad_header";
        return std::nullopt;
    }
    if (!doc["payload"].is<ArduinoJson::JsonObject>()) {
        if (error_code) *error_code = "bad_payload";
        return std::nullopt;
    }

    Command cmd;
    cmd.id   = doc["id"].as<const char*>();
    cmd.type = ParseMsgType(doc["type"].as<const char*>());
    auto payload = doc["payload"].as<ArduinoJson::JsonObject>();

    switch (cmd.type) {
        case MsgType::HelloOk:
            if (payload["session_id"].is<const char*>()) {
                cmd.session_id = payload["session_id"].as<const char*>();
            }
            break;
        case MsgType::TextShow:
            if (!payload["text"].is<const char*>()) {
                if (error_code) *error_code = "bad_text";
                return std::nullopt;
            }
            cmd.text = payload["text"].as<const char*>();
            if (cmd.text.size() > kMaxTextChars) {
                cmd.text.resize(kMaxTextChars);
            }
            cmd.partial = payload["partial"] | false;
            break;
        case MsgType::ExpressionSet:
            if (!payload["name"].is<const char*>() || !IsAllowedExpression(payload["name"].as<const char*>())) {
                if (error_code) *error_code = "bad_expression";
                return std::nullopt;
            }
            cmd.name        = payload["name"].as<const char*>();
            cmd.duration_ms = payload["duration_ms"] | 0;
            break;
        case MsgType::AnimationPlay:
            if (!payload["name"].is<const char*>() || !IsAllowedAnimation(payload["name"].as<const char*>())) {
                if (error_code) *error_code = "bad_animation";
                return std::nullopt;
            }
            cmd.name        = payload["name"].as<const char*>();
            if (cmd.name == "reading") {
                cmd.name = "read";
            }
            cmd.duration_ms = payload["duration_ms"] | 0;
            cmd.loop        = payload["loop"] | false;
            break;
        case MsgType::MotionSet: {
            float yaw   = payload["yaw_deg"] | 0.0f;
            float pitch = payload["pitch_deg"] | 0.0f;
            int speed   = payload["speed"] | 200;
            // 超出硬性範圍直接拒絕，不靜默執行危險角度
            if (yaw < kYawDegMin || yaw > kYawDegMax || pitch < kPitchDegMin || pitch > kPitchDegMax ||
                speed < kSpeedMin || speed > kSpeedMax) {
                if (error_code) *error_code = "motion_limit";
                return std::nullopt;
            }
            cmd.yaw_deg   = ClampFloat(yaw, kYawDegMin, kYawDegMax);
            cmd.pitch_deg = ClampFloat(pitch, kPitchDegMin, kPitchDegMax);
            cmd.speed     = ClampInt(speed, kSpeedMin, kSpeedMax);
            break;
        }
        case MsgType::StateSet:
            if (!payload["state"].is<const char*>()) {
                if (error_code) *error_code = "bad_state";
                return std::nullopt;
            }
            cmd.state = payload["state"].as<const char*>();
            break;
        case MsgType::PetState:
            cmd.name = payload["action"].is<const char*>() ? payload["action"].as<const char*>() : "idle";
            break;
        case MsgType::Stop:
        case MsgType::Heartbeat:
        case MsgType::Ack:
            cmd.ok = payload["ok"] | true;
            if (payload["error"].is<const char*>()) {
                cmd.error_code = payload["error"].as<const char*>();
            }
            break;
        case MsgType::Unknown:
        default:
            if (error_code) *error_code = "unknown_type";
            return std::nullopt;
    }
    return cmd;
}

namespace {

std::string FormatEnvelope(const char* type, const char* id, std::string_view payload_json)
{
    char header[128];
    std::snprintf(header, sizeof(header), R"({"v":1,"id":"%s","type":"%s","payload":)", id, type);
    std::string out = header;
    out.append(payload_json);
    out.push_back('}');
    return out;
}

}  // namespace

std::string MakeHelloJson(std::string_view device_id, std::string_view firmware_version)
{
    ArduinoJson::JsonDocument doc;
    doc["device_id"]         = device_id;
    doc["firmware_version"]  = firmware_version;
    doc["mode"]              = "companion";
    auto caps                = doc["caps"].to<ArduinoJson::JsonArray>();
    caps.add("text");
    caps.add("expression");
    caps.add("motion");
    caps.add("animation");
    std::string payload;
    ArduinoJson::serializeJson(doc, payload);
    return FormatEnvelope("hello", "hello-1", payload);
}

std::string MakeHeartbeatJson(uint32_t uptime_ms, std::string_view state)
{
    char payload[96];
    std::snprintf(payload, sizeof(payload), R"({"uptime_ms":%u,"state":"%.*s"})", static_cast<unsigned>(uptime_ms),
                  static_cast<int>(state.size()), state.data());
    return FormatEnvelope("heartbeat", "hb-1", payload);
}

std::string MakeStopJson(std::string_view reason)
{
    char payload[64];
    std::snprintf(payload, sizeof(payload), R"({"scope":"all","reason":"%.*s"})", static_cast<int>(reason.size()),
                  reason.data());
    return FormatEnvelope("stop", "stop-1", payload);
}

std::string MakeDeviceModeJson(std::string_view mode, bool active)
{
    char payload[96];
    std::snprintf(payload, sizeof(payload), R"({"mode":"%.*s","active":%s})", static_cast<int>(mode.size()),
                  mode.data(), active ? "true" : "false");
    return FormatEnvelope("device.mode", "mode-1", payload);
}

std::string MakeTouchJson(std::string_view zone, std::string_view action)
{
    char payload[96];
    std::snprintf(payload, sizeof(payload), R"({"zone":"%.*s","action":"%.*s"})", static_cast<int>(zone.size()),
                  zone.data(), static_cast<int>(action.size()), action.data());
    return FormatEnvelope("interaction.touch", "touch-1", payload);
}

std::string MakeAckJson(std::string_view reply_to, bool ok)
{
    char payload[96];
    std::snprintf(payload, sizeof(payload), R"({"reply_to":"%.*s","ok":%s})", static_cast<int>(reply_to.size()),
                  reply_to.data(), ok ? "true" : "false");
    return FormatEnvelope("ack", "ack-1", payload);
}

}  // namespace companion
