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
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

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
 * - Connect 在背景 task 執行，避免阻塞 LVGL／Mooncake 主迴圈（假當機）
 * - 回呼只入隊，不直接操作 LVGL／馬達；由 App onRunning 抽取
 */
class CompanionClient {
public:
    CompanionClient();
    ~CompanionClient();

    void start(std::string ws_url, std::string token, std::string device_id);
    void stop();

    /** Connect 背景 task 仍在跑（含 TCP timeout 中） */
    bool isConnectInFlight() const
    {
        return _connect_task != nullptr;
    }

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
    void connect_worker();
    void enqueue(Command cmd);
    void set_link(LinkState state);
    void join_connect_task();

    static void connect_task_entry(void* arg);

    std::string _ws_url;
    std::string _token;
    std::string _device_id;
    std::string _session_id;

    std::unique_ptr<WebSocket> _ws;
    mutable std::mutex _mutex;
    std::deque<Command> _queue;
    std::atomic<LinkState> _link_state{LinkState::Idle};
    std::atomic<uint32_t> _missed_heartbeats{0};
    std::atomic<uint32_t> _generation{0};
    std::atomic<bool> _stop_requested{false};
    uint32_t _last_heartbeat_tx_ms = 0;
    bool _hello_sent               = false;

    TaskHandle_t _connect_task           = nullptr;
    SemaphoreHandle_t _connect_done_sem  = nullptr;
};

}  // namespace companion
