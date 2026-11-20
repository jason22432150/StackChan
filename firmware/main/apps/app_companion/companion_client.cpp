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
#include <wifi_manager.h>

namespace companion {
namespace {
constexpr std::string_view kTag = "CompanionWS";
constexpr uint32_t kConnectStack = 6144;
constexpr UBaseType_t kConnectPrio = 5;
}  // namespace

CompanionClient::CompanionClient()
{
    _connect_done_sem = xSemaphoreCreateBinary();
}

CompanionClient::~CompanionClient()
{
    stop();
    if (_connect_done_sem) {
        vSemaphoreDelete(_connect_done_sem);
        _connect_done_sem = nullptr;
    }
}

void CompanionClient::start(std::string ws_url, std::string token, std::string device_id)
{
    // 取消進行中的連線，但不要在此 join（TCP timeout 可達十數秒，會堵死 Mooncake 主迴圈）
    // 重要：Connect 期間只 Close、不 reset，避免 use-after-free → heap 損壞 → StoreProhibited
    _stop_requested.store(true);
    _generation.fetch_add(1);
    {
        std::lock_guard<std::mutex> lock(_mutex);
        if (_ws) {
            _ws->Close();
        }
    }

    if (_connect_task != nullptr) {
        mclog::tagWarn(kTag, "previous connect still in flight, defer new start");
        set_link(LinkState::Connecting);
        return;
    }

    {
        std::lock_guard<std::mutex> lock(_mutex);
        _ws.reset();
        _queue.clear();
        _session_id.clear();
    }

    _ws_url     = std::move(ws_url);
    _token      = std::move(token);
    _device_id  = std::move(device_id);
    _hello_sent = false;
    _missed_heartbeats.store(0);
    _stop_requested.store(false);
    set_link(LinkState::Connecting);

    if (!_connect_done_sem) {
        mclog::tagError(kTag, "connect semaphore missing");
        set_link(LinkState::Offline);
        return;
    }
    xSemaphoreTake(_connect_done_sem, 0);

    // Connect 可能卡在不可達 IP 十數秒；必須離主迴圈，否則畫面假死、home 無反應
    if (xTaskCreate(&CompanionClient::connect_task_entry, "comp_ws", kConnectStack, this, kConnectPrio,
                    &_connect_task) != pdPASS) {
        _connect_task = nullptr;
        mclog::tagError(kTag, "failed to start connect task");
        set_link(LinkState::Offline);
        return;
    }
}

void CompanionClient::stop()
{
    _stop_requested.store(true);
    _generation.fetch_add(1);

    {
        std::lock_guard<std::mutex> lock(_mutex);
        if (_ws) {
            // 打斷進行中的 Connect／收送；物件生命週期保留到 join 之後再釋放
            if (_link_state.load() == LinkState::Online) {
                _ws->Send(MakeDeviceModeJson("launcher", false));
            }
            _ws->Close();
        }
    }

    join_connect_task();

    {
        std::lock_guard<std::mutex> lock(_mutex);
        _ws.reset();
        _queue.clear();
        _session_id.clear();
    }
    set_link(LinkState::Idle);
}

void CompanionClient::join_connect_task()
{
    if (!_connect_done_sem) {
        _connect_task = nullptr;
        return;
    }
    if (!_connect_task) {
        xSemaphoreTake(_connect_done_sem, 0);
        return;
    }
    // Connect timeout 約 10s；給足夠時間讓 task 收尾
    if (xSemaphoreTake(_connect_done_sem, pdMS_TO_TICKS(15000)) != pdTRUE) {
        mclog::tagWarn(kTag, "connect task join timeout");
    }
    _connect_task = nullptr;
}

void CompanionClient::connect_task_entry(void* arg)
{
    auto* self = static_cast<CompanionClient*>(arg);
    self->connect_worker();
    // 先通知 join，再自刪；_connect_task 由 join 端清空，避免雙寫競態
    if (self->_connect_done_sem) {
        xSemaphoreGive(self->_connect_done_sem);
    }
    vTaskDelete(nullptr);
}

void CompanionClient::sendText(const std::string& json)
{
    std::lock_guard<std::mutex> lock(_mutex);
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
        std::lock_guard<std::mutex> lock(_mutex);
        if (_ws) {
            _ws->Close();
        }
    }
}

void CompanionClient::connect_worker()
{
    const uint32_t gen = _generation.load();
    if (_stop_requested.load()) {
        set_link(LinkState::Offline);
        return;
    }

    if (!WifiManager::GetInstance().IsConnected()) {
        mclog::tagWarn(kTag, "wifi not connected, skip websocket connect");
        set_link(LinkState::Offline);
        return;
    }

    auto* network = Board::GetInstance().GetNetwork();
    if (!network) {
        mclog::tagError(kTag, "network unavailable");
        set_link(LinkState::Offline);
        return;
    }

    auto ws = network->CreateWebSocket(31);
    if (!ws) {
        mclog::tagError(kTag, "CreateWebSocket failed");
        set_link(LinkState::Offline);
        return;
    }

    if (!_token.empty()) {
        ws->SetHeader("X-StackChan-Token", _token.c_str());
    }

    ws->OnConnected([this, gen]() {
        if (_stop_requested.load() || _generation.load() != gen) {
            return;
        }
        mclog::tagInfo(kTag, "connected");
        set_link(LinkState::Online);
        _missed_heartbeats.store(0);
        if (!_hello_sent) {
            _hello_sent = true;
            sendText(MakeHelloJson(_device_id, common::FirmwareVersion));
        }
    });

    ws->OnDisconnected([this, gen]() {
        if (_generation.load() != gen) {
            return;
        }
        mclog::tagWarn(kTag, "disconnected");
        set_link(LinkState::Offline);
    });

    ws->OnError([this, gen](const NetworkError& error) {
        if (_generation.load() != gen) {
            return;
        }
        mclog::tagError(kTag, "ws error: {}", error.ToString());
        set_link(LinkState::Offline);
    });

    ws->OnData([this, gen](const char* data, size_t len, bool binary) {
        if (_stop_requested.load() || _generation.load() != gen) {
            return;
        }
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

    auto log_url = url;
    const auto token_pos = log_url.find("token=");
    if (token_pos != std::string::npos) {
        auto end = log_url.find_first_of("&", token_pos);
        if (end == std::string::npos) {
            end = log_url.size();
        }
        log_url.replace(token_pos, end - token_pos, "token=***");
    }

    {
        std::lock_guard<std::mutex> lock(_mutex);
        if (_stop_requested.load() || _generation.load() != gen) {
            set_link(LinkState::Offline);
            return;
        }
        _ws = std::move(ws);
    }

    // Connect 可能阻塞十數秒，且成功時會同步觸發 OnConnected→sendText；
    // 不可持有 _mutex，否則死鎖。stop() 只會 Close、不會在 join 前 reset。
    mclog::tagInfo(kTag, "connecting {}", log_url);
    bool ok = false;
    {
        WebSocket* raw = nullptr;
        {
            std::lock_guard<std::mutex> lock(_mutex);
            raw = _ws.get();
        }
        if (raw) {
            ok = static_cast<bool>(raw->Connect(url.c_str()));
        }
    }

    if (_stop_requested.load() || _generation.load() != gen) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (_ws) {
            _ws->Close();
        }
        set_link(LinkState::Offline);
        return;
    }

    if (!ok) {
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
