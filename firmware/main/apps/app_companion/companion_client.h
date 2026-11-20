/*
 * SPDX-FileCopyrightText: 2026 M5Stack Technology CO LTD
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include "companion_protocol.h"
#include <atomic>
#include <cstdint>
#include <deque>
#include <memory>
#include <mutex>
#include <string>

class WebSocket;

namespace companion {

enum class LinkState {
    Idle,
    Connecting,
    Online,
    Offline,
};

/**
 * @brief Companion ↔ Pi WebSocket 客戶端。
 *
 * 回呼只入隊，不直接操作 LVGL／馬達；由 App onRunning 抽取。
 */
class CompanionClient {
public:
    CompanionClient();
    ~CompanionClient();

    void start(std::string ws_url, std::string token, std::string device_id);
    void stop();

    void sendText(const std::string& json);
    bool popCommand(Command& out);
    LinkState linkState() const
    {
        return _link_state.load();
    }
    std::string sessionId() const;
    uint32_t missedHeartbeats() const
    {
        return _missed_heartbeats.load();
    }
    void onHeartbeatPong();
    void tickHeartbeat(uint32_t now_ms, uint32_t interval_ms);

private:
    void connect_async();
    void enqueue(Command cmd);
    void set_link(LinkState state);

    std::string _ws_url;
    std::string _token;
    std::string _device_id;
    std::string _session_id;

    std::unique_ptr<WebSocket> _ws;
    mutable std::mutex _mutex;
    std::deque<Command> _queue;
    std::atomic<LinkState> _link_state{LinkState::Idle};
    std::atomic<uint32_t> _missed_heartbeats{0};
    uint32_t _last_heartbeat_tx_ms = 0;
    bool _hello_sent               = false;
};

}  // namespace companion
