# AppCompanion（Phase 1）

Mooncake 獨立 App：連線 Raspberry Pi Coordinator，顯示文字／表情／活動，並執行安全範圍內的轉頭。

## 能力（本階段）

- 開啟時先 `startNetwork()`（與原廠 Avatar 相同），再連 Pi；避免 lwIP Invalid mbox 當機
- WebSocket：`hello` / `hello.ok` / `heartbeat` / `ack`
- 接收：`text.show`、`expression.set`、`animation.play`、`motion.set`、`state.set`、`stop`
- 觸控 **STOP**：先停本機馬達／字幕，再通知 Pi
- Pi 離線：顯示 offline、本機 IdleMotion，自動重連；可回 Launcher
- 退出：`device.mode=launcher`、關閉 socket、`resetAvatar`、停馬達

## 建置期 `.env`（本機，勿提交）

ESP32 **執行期不會讀** 開發機上的 `.env`；改為 **建置時** 由 CMake 注入預設值。

```bash
cd firmware/main/apps/app_companion
cp .env.example .env
# 編輯 COMPANION_PI_WS_URL=ws://<Pi-IP>:8765/ws/device
cd ../../..   # → firmware/
idf.py reconfigure build
```

| 鍵 | 說明 |
|---|---|
| `COMPANION_PI_WS_URL` | 燒進韌體的預設 WS URL |
| `COMPANION_PI_TOKEN` | 預設 LAN token（可空） |

## NVS 設定（一般 NVS，非 eFuse）

namespace `companion`（執行期優先於建置預設）：

| key | 說明 | 預設來源 |
|---|---|---|
| `pi_ws_url` | Pi WebSocket URL | `.env` → 否則 `ws://192.168.1.1:8765/ws/device` |
| `pi_token` | LAN Token（可空＝開發模式） | `.env` → 否則 `""` |

若 NVS 已寫過舊 URL，只改 `.env` 重編不會覆蓋；需清 NVS 或之後用設定頁更新。

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
