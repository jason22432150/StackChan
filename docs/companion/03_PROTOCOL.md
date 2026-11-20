# 03｜Companion 通訊協定草案 v1.1

> 此協定為**新設計**，不是原廠 Avatar WebSocket 的直接相容宣告。開發時先讓 ESP32-S3 與 Pi 兩端對齊，再以實機測試修訂。

## 1. 通道及連線
- StackChan 主動連至 Pi `ws://<pi-ip>:8765/ws/device`，僅允許已配對裝置／LAN 連入；不得將服務 Port Forward 到網際網路。
- Pi `POST /api/events` 接收電腦 Bridge 事件（使用獨立 Token）；無論模式均可紀錄，但**只有 Companion 開啟時能送通知顯示/播報**。
- 內網 `/health` 僅讀健康狀態；`/api/config` 等變更設定的 API 必須驗證。
- 一條 WebSocket 同時傳 JSON 控制與二進位音訊影格；不允許控制 callback 直接阻塞渲染。

## 2. 控制訊息
```json
{"v":1,"id":"msg-00018","type":"animation.play","ts_ms":1795000000000,"payload":{"name":"reading","duration_ms":10000}}
```
- `v` 版本；`id` 去重／回覆；`type` 指令種類；`ts_ms` 可選；`payload` 必填。
- 重要控制指令回 `ack`。未知類型僅回錯，不崩潰；所有字串長度、數值、音訊封包都需設上限。

## 3. 核心事件與方向
| 方向 | type | 主要 payload |
|---|---|---|
| SC→Pi | `hello` | `device_id`, `firmware_version`, `caps`, `mode=companion` |
| Pi→SC | `hello.ok` | `session_id`, `protocol_version`, `settings` |
| 雙向 | `heartbeat` | `uptime_ms`, `state` |
| SC→Pi | `interaction.touch` | `zone`, `action` |
| SC→Pi | `wake.detected` | `source=touch|keyword`, `keyword_id`（如有） |
| 雙向 | `audio.begin` / `audio.end` | `stream_id`, `codec`, `sample_rate`, `channels`, `reason` |
| SC→Pi | `dialogue.cancel` | `turn_id`, `reason=touch` |
| Pi→SC | `text.show` | `text`, `partial`, `turn_id` |
| Pi→SC | `expression.set` | `name`, `duration_ms` |
| Pi→SC | `motion.set` | `yaw_deg`, `pitch_deg`, `speed` |
| Pi→SC | `animation.play` | `name`, `duration_ms`, `loop` |
| Pi→SC | `state.set` | `IDLE/LISTENING/THINKING/SPEAKING/NOTIFYING/OFFLINE` |
| Pi→SC | `pet.state` | `mood`, `energy`, `affinity`, `activity`, `action` |
| SC→Pi | `device.mode` | `mode=companion|launcher|factory_ai`, `active` |
| SC→Pi | `playback.done` | `turn_id`, `stream_id` |
| 雙向 | `stop` / `ack` | `scope`, `reply_to`, `ok` |

### 模式隔離
- Pi 維護 `device_mode`，只有經 `hello` 建立的 **Companion 活動連線** 才能發送通知 UI/音效指令。
- `launcher` 或 `factory_ai` 模式下不推送 `notification.*`、`text.show` 或自行動作來打斷原廠模式；收到 Agent 事件僅在 Pi 儲存。
- 重新連入 Companion 才能要求 `notifications.unread_summary`；摘要需去重、有最大數量與保存時限。

## 4. 二進位音訊影格（設計）
```
Byte 0..3   magic = 'SCA1'
Byte 4      frame version=1
Byte 5      codec_id 1=PCM16_LE / 2=Opus
Byte 6..7   reserved
Byte 8..11  stream_id uint32 BE
Byte 12..15 sequence uint32 BE
Byte 16..  audio payload
```
- 建議 MVP 首先支援 `PCM16_LE 16kHz mono` 上行；下行採裝置能力協商（優先可用 PCM/Opus）。
- `audio.begin` 提供 codec、sample rate、channels；不猜測既有原廠音訊編碼必定互通。
- 語音上行可能有兩種場景：**低負載喚醒偵測**與**真正問答收音**，兩者由不同狀態控制，不能把持續音訊誤當成完整對話。
- 有界音訊佇列、序號檢查、異常丟棄／回錯；預設不將原始錄音長期存檔。
- 觸控取消時，StackChan 先**立即停喇叭**，再傳 `dialogue.cancel`；Pi 停止正在生成或等待的音訊，舊 `turn_id` 回應全部丟棄。

## 5. AI 自主行為訊息
Pi 本地呼叫 LLM，經驗證後才送白名單 `animation.play`、`expression.set`、`text.show`、`motion.set`。**不要將 LLM 任意 JSON 直接作為 StackChan 指令，也不要在網路訊息執行 shell 指令。**

## 6. 重連、配對與心跳
- 以簡單短時效配對碼換取 Pi/設備一般儲存 Token，不動 eFuse。
- 心跳建議每 5 秒，連續 3 次丟失視為 OFFLINE；作為初始設定，依實測修正。
- 斷線不堆疊音訊影格；Pi 的寵物狀態/重要事件寫 SQLite，重連只同步**最新快照**，不重播過期逐幀指令。
- Pi 模型切換屬 Pi 端 `/api/config`／本機設定，不要求 StackChan 重新燒錄。

## v2.3.3：自主活動與主動互動指令（協定增補）
以下為**提案介面**，需兩端一起實作並版本驗證；不可聲稱與原廠 Avatar 協定即插即用。

Pi → StackChan（活動計畫；含唯一識別與時效）
```json
{"v":1,"id":"cmd-201","type":"pet.activity","payload":{"activity_id":"a-202","action":"read","mood":"curious","duration_s":480,"interruptible":true,"expires_at_ms":1795000060000}}
```

Pi → StackChan（可選，不保證一定要播放）
```json
{"v":1,"id":"cmd-202","type":"pet.proactive","payload":{"kind":"text_bubble","text":"我想再看一頁書。","ttl_ms":9000,"activity_id":"a-202"}}
```

StackChan → Pi（回饋）
```json
{"v":1,"id":"evt-201","type":"pet.activity.completed","payload":{"activity_id":"a-202","reason":"completed"}}
```

### 必須實作的協定規則
- `pet.activity` 僅接受活動白名單 `idle/sleep/read/work/eat/walk/explore/create/look_around/celebrate`；不接受任意命令、檔案路徑或模型下發的馬達角度。
- `pet.proactive` 僅供經 Pi Proactivity Gate 許可的低頻短語；`kind=voice` 必須經音訊會話檢查，文字泡泡逾期不重播。
- 控制與音訊擁有明確 `turn_id`、`stream_id` 或 `activity_id`；過期訊息不執行，取消後遲到的回覆全部丟棄。
- 保留原先 `animation.play` 等低階白名單訊息，兩者不可對同一時段的 UI/馬達並行強制控制，由 Activity Controller 仲裁。
- 設備切回 Launcher 或進入原廠 Xiaozhi 前關閉 Companion WebSocket；**Pi 不得推入任何 Companion 音訊／動畫／通知**。若無明確回報，無 Companion 活躍會話即視為不可推送。
- 先規定大小限制與背壓：文字內容長度、音訊分段大小、單向待處理數量、緩衝延遲要有上限；具體數字在 Phase 1/2 實測後定稿。
