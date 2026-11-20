/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#include "companion_client.h"
#include <board.h>
#include <mooncake_log.h>
#include <apps/common/common.h>
#include <web_socket.h>
#include <network_error.h>

namespace companion {
namespace {
constexpr std::string_view kTag = "CompanionWS";
}

CompanionClient::CompanionClient() = default;

CompanionClient::~CompanionClient()
{
    stop();
}

void CompanionClient::start(std::string ws_url, std::string token, std::string device_id)
{
    stop();
    _ws_url    = std::move(ws_url);
    _token     = std::move(token);
    _device_id = std::move(device_id);
    _hello_sent = false;
    _missed_heartbeats.store(0);
    set_link(LinkState::Connecting);
    connect_async();
}

void CompanionClient::stop()
{
    if (_ws) {
        // 通知 Pi：Companion 即將退出，不可再推 UI
        if (_link_state.load() == LinkState::Online) {
            _ws->Send(MakeDeviceModeJson("launcher", false));
        }
        _ws->Close();
        _ws.reset();
    }
    {
        std::lock_guard<std::mutex> lock(_mutex);
        _queue.clear();
        _session_id.clear();
    }
    set_link(LinkState::Idle);
}

void CompanionClient::sendText(const std::string& json)
{
    if (_ws && _ws->IsConnected()) {
        _ws->Send(json);
    }
}

bool CompanionClient::popCommand(Command& out)
{
    std::lock_guard<std::mutex> lock(_mutex);
    if (_queue.empty()) {
        return false;
    }
    out = std::move(_queue.front());
    _queue.pop_front();
    return true;
}

std::string CompanionClient::sessionId() const
{
    std::lock_guard<std::mutex> lock(_mutex);
    return _session_id;
}

void CompanionClient::onHeartbeatPong()
{
    _missed_heartbeats.store(0);
}

void CompanionClient::tickHeartbeat(uint32_t now_ms, uint32_t interval_ms)
{
    if (_link_state.load() != LinkState::Online) {
        return;
    }
    if (now_ms - _last_heartbeat_tx_ms < interval_ms) {
        return;
    }
    _last_heartbeat_tx_ms = now_ms;
    _missed_heartbeats.fetch_add(1);
    sendText(MakeHeartbeatJson(now_ms, "IDLE"));
    if (_missed_heartbeats.load() >= 3) {
        mclog::tagWarn(kTag, "heartbeat timeout → offline");
        set_link(LinkState::Offline);
        if (_ws) {
            _ws->Close();
        }
    }
}

void CompanionClient::connect_async()
{
    auto* network = Board::GetInstance().GetNetwork();
    if (!network) {
        mclog::tagError(kTag, "network unavailable");
        set_link(LinkState::Offline);
        return;
    }

    // 使用獨立 connect_id，避免與 Avatar/Xiaozhi 服務衝突
    _ws = network->CreateWebSocket(31);
    if (!_ws) {
        mclog::tagError(kTag, "CreateWebSocket failed");
        set_link(LinkState::Offline);
        return;
    }

    if (!_token.empty()) {
        _ws->SetHeader("X-StackChan-Token", _token.c_str());
    }

    _ws->OnConnected([this]() {
        mclog::tagInfo(kTag, "connected");
        set_link(LinkState::Online);
        _missed_heartbeats.store(0);
        if (!_hello_sent) {
            _hello_sent = true;
            sendText(MakeHelloJson(_device_id, common::FirmwareVersion));
        }
    });

    _ws->OnDisconnected([this]() {
        mclog::tagWarn(kTag, "disconnected");
        set_link(LinkState::Offline);
    });

    _ws->OnError([this](const NetworkError& error) {
        mclog::tagError(kTag, "ws error: {}", error.ToString());
        set_link(LinkState::Offline);
    });

    _ws->OnData([this](const char* data, size_t len, bool binary) {
        if (binary || data == nullptr || len == 0) {
            return;
        }
        std::string json(data, len);
        std::string error;
        auto cmd = ParseCommand(json, &error);
        if (!cmd) {
            mclog::tagWarn(kTag, "drop message: {}", error);
            return;
        }
        if (cmd->type == MsgType::Heartbeat || cmd->type == MsgType::Ack) {
            onHeartbeatPong();
        }
        if (cmd->type == MsgType::HelloOk) {
            std::lock_guard<std::mutex> lock(_mutex);
            _session_id = cmd->session_id;
        }
        enqueue(std::move(*cmd));
    });

    std::string url = _ws_url;
    if (!_token.empty() && url.find('?') == std::string::npos) {
        url.append("?token=").append(_token);
    } else if (!_token.empty()) {
        url.append("&token=").append(_token);
    }

    // 避免把 token 打進 log
    auto log_url = url;
    const auto token_pos = log_url.find("token=");
    if (token_pos != std::string::npos) {
        auto end = log_url.find_first_of("&", token_pos);
        if (end == std::string::npos) {
            end = log_url.size();
        }
        log_url.replace(token_pos, end - token_pos, "token=***");
    }
    mclog::tagInfo(kTag, "connecting {}", log_url);
    auto result = _ws->Connect(url.c_str());
    if (!result) {
        mclog::tagError(kTag, "connect failed");
        set_link(LinkState::Offline);
    }
}

void CompanionClient::enqueue(Command cmd)
{
    std::lock_guard<std::mutex> lock(_mutex);
    if (_queue.size() >= kMaxQueueDepth) {
        _queue.pop_front();
    }
    _queue.push_back(std::move(cmd));
}

void CompanionClient::set_link(LinkState state)
{
    _link_state.store(state);
}

}  // namespace companion
