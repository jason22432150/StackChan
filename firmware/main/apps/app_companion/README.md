# AppCompanion（Phase 1）

Mooncake 獨立 App：連線 Raspberry Pi Coordinator，顯示文字／表情／活動，並執行安全範圍內的轉頭。

## 能力（本階段）

- 開啟時先 `startNetwork()`（與原廠 Avatar 相同），再連 Pi；避免 lwIP Invalid mbox 當機
- WebSocket：`hello` / `hello.ok` / `heartbeat` / `ack`
- 接收：`text.show`、`expression.set`、`animation.play`、`motion.set`、`state.set`、`stop`
- 觸控 **STOP**：先停本機馬達／字幕，再通知 Pi
- Pi 離線：顯示 offline、本機 IdleMotion，自動重連；可回 Launcher
- 退出：`device.mode=launcher`、關閉 socket、`resetAvatar`、停馬達

## NVS 設定（一般 NVS，非 eFuse）

namespace `companion`：

| key | 說明 | 預設 |
|---|---|---|
| `pi_ws_url` | Pi WebSocket URL | `ws://192.168.1.1:8765/ws/device` |
| `pi_token` | LAN Token（可空＝開發模式） | `""` |

## 不做（留給後續 Phase）

- 音訊上行／下行、喚醒詞、雲端 STT/LLM/TTS
- `boot_mode` 開機直入
- microSD 設定頁
- 完整活動動畫素材（目前以表情＋字幕＋輕轉頭代替）

## 生命週期清理

| 資源 | onOpen | onClose |
|---|---|---|
| LVGL UI / STOP 鈕 | 建立 | destroy |
| DefaultAvatar + modifiers | 建立 | clear + resetAvatar |
| WebSocket | 連線 | stop + device.mode inactive |
| 馬達 | 可被指令驅動 | stop + goHome |
