# 18｜Phase 1 實機問題紀錄（問題／原因／解法）

> 日期：2026-11-20  
> 分支：`feature/stackchan-companion`  
> 硬體：M5Stack StackChan（ESP32-S3）＋ USB serial `/dev/cu.usbmodem1101`  
> 範圍：Phase 1 連線／UI／動作實機驗證期間踩到的問題  
> 原則：禁止 eFuse、不破壞原廠 Xiaozhi；退出允許 warm reboot

---

## 總覽

| ID | 現象 | 根因類型 | 狀態 |
|---|---|---|---|
| F-01 | 進入 Companion 立刻重啟 | 主執行緒同步 WS Connect → lwIP assert | 已修 |
| F-02 | 連網後無法返回主頁 | UI z-order；退出未 warm reboot | 已修 |
| F-03 | 看起來「當機」約 10 秒 | 主迴圈同步 TCP Connect timeout | 已修 |
| F-04 | 連線失敗後持續假死／WDT | IDLE0 被主迴圈餓死 | 已修 |
| F-05 | Pi 永遠連不上（預期） | 預設 `pi_ws_url` 與區網不符 | 待設定 |
| F-06 | 退出 Companion 時 StoreProhibited | Connect 中 `reset` WebSocket → heap 損壞 | 已修 |

---

## F-01｜進入 Companion 立刻重啟（panic）

### 問題
開啟 Companion 後裝置重啟。Serial 可見 `tcpip_send_msg_wait_sem`／`Invalid mbox` assert（WebSocket `Connect` → `getaddrinfo` 時 lwIP 未就緒）。

### 原因
- 未先呼叫與原廠 Avatar 相同的 `GetHAL().startNetwork()`。
- 在 Wi-Fi／lwIP 未啟動時建立 WebSocket，觸發 lwIP assert → 重啟。
- 此為 **panic 重啟**，不是規格允許的 warm reboot。

### 解決方法
1. `onOpen`：先顯示 LoadingPage → `startNetwork()` → 再建 UI／avatar／WS。
2. 重連前檢查 `WifiManager::IsConnected()`；Wi-Fi 未連線則跳過 Connect。
3. `CompanionClient` 內雙重防護：未連線不呼叫 `Connect`。

### 關鍵位置
- `firmware/main/apps/app_companion/app_companion.cpp`（`onOpen`／重連）
- `firmware/main/apps/app_companion/companion_client.cpp`

---

## F-02｜無法觸發返回主頁；連網後只看到臉

### 問題
- 進入 Companion、Wi-Fi 連上後畫面是 StackChan 臉。
- 底部上滑／home 無法回到 Launcher。

### 原因
1. **臉是正確的**：Phase 1 待機就是本機 `DefaultAvatar`（表情／字幕／動作承載面），與原廠 Avatar 一致。
2. **層級錯誤**：先 `create_home_indicator`，後建立全螢幕 avatar → 臉蓋住 home／STOP／狀態。
3. **退出路徑不完整**：僅 `close()`，未走 Avatar／Dance 慣用的 `requestWarmReboot(index)`；插入 Companion 後 Setup 的 warm reboot index 也需 +1。

### 解決方法
1. 建立順序改為：UI 骨架 → `setup_avatar` → **再** `create_home_indicator`／`create_status_bar`。
2. Avatar 掛在 `_root` 下，並 `raise_overlays()` 把 STOP／狀態抬到臉之上；avatar panel 移除 `CLICKABLE`。
3. `onClose` 呼叫 `GetHAL().requestWarmReboot(6)`（unfiltered 列表中 COMPANION index）。
4. Setup 的 warm reboot index 由 `6` 改為 `7`。

### 操作提醒（原廠手勢）
1. 螢幕**底部往上滑** → 出現 home 鍵  
2. 再點 home → warm reboot 回 Launcher  

### 關鍵位置
- `app_companion.cpp`：`onOpen`／`setup_avatar`／`raise_overlays`／`onClose`
- `app_setup.cpp`：warm reboot index

---

## F-03｜連 Pi 失敗時整機「假死」約 10 秒

### 問題
Serial：`CompanionWS connecting ws://192.168.1.1:8765/...` → 約 10 秒後 `Connection timed out`／`connect failed`。期間觸控無反應，易被誤認為當機。**無 Guru Meditation。**

### 原因
- 預設 URL `ws://192.168.1.1:8765/ws/device` 與實機區網（例：`192.168.50.x`）不符，TCP 必 timeout。
- `WebSocket::Connect()` 在 **Mooncake 主迴圈**同步執行，timeout 期間 `onRunning`／home 手勢都不跑。

### 解決方法
1. `CompanionClient::start()` 以 FreeRTOS task（`comp_ws`）執行 Connect；主迴圈立即返回。
2. `stop()`／generation 取消進行中連線；回呼帶 generation 防過期。
3. **真正連 Pi**：把 NVS `companion.pi_ws_url`（與可選 `pi_token`）設成實際 Pi IP，例如 `ws://192.168.50.xx:8765/ws/device`。

### 關鍵位置
- `companion_client.cpp`／`.h`：`connect_worker`／`connect_task_entry`

---

## F-04｜connect failed 後持續 task_wdt（IDLE0）假死

### 問題
Pi 連線 timeout 後 Serial 每約 10 秒：

```text
task_wdt: IDLE0 (CPU 0)
CPU 0: main
backtrace → AppCompanion::onRunning → update_home_indicator → setPos
```

裝置持續無回應（非單次 panic）。

### 原因
1. `onRunning` 對 LVGL／home／avatar 更新**未整段持 `LvglLockGuard`**（與 Avatar 不同），無鎖 `setPos`／invalidate 與 LVGL task 競態，CPU0 被拖死 → IDLE0 無法餵 WDT。
2. 離線自動重連在主迴圈呼叫 `start()`→`stop()`→**同步 join** 背景 Connect task；若仍在 TCP timeout，主迴圈可被堵住十數秒。

### 解決方法
1. `onRunning` 整段 UI／`GetStackChan().update()`／home／status 持 `LvglLockGuard`（對齊 Avatar）。
2. `start()` **不再 join** 舊 Connect task（只 Close＋generation）；`onClose` 的 `stop()` 仍可 join 收尾。
3. 重連前若 `isConnectInFlight()` 則跳過，避免重入。

### 關鍵位置
- `app_companion.cpp`：`onRunning`／`drain_commands_locked` 等
- `companion_client.cpp`：`start`（非阻塞）／`stop`（關閉時 join）

---

## F-06｜退出 Companion 時 Guru Meditation（StoreProhibited）

### 問題
Serial 在 `COMPANION on close` 後出現：

```text
EspTcp: Connection failed
Guru Meditation Error: Core 1 panic'ed (StoreProhibited)
backtrace → tlsf_free → vPortFree → prvDeleteTCB
```

裝置重啟。此前 **無** 連續 `task_wdt`；STOP 在連線中可正常 `stopAll: touch`。

### 原因
背景 task 正在 `WebSocket::Connect()` 時，`stop()`／`start()` 對 `_ws` 做 `Close()` **並立刻 `reset()`**，把仍被 Connect 使用的物件釋放 → heap 損壞；隨後 FreeRTOS 回收 `comp_ws` task TCB 時在 `tlsf_free` 爆炸。

### 解決方法
1. Connect 進行中只 `Close()` 打斷，**join 完成後再 `_ws.reset()`**。
2. `connect_worker` 取消路徑也不再提前 `reset`。
3. task 結束只 `xSemaphoreGive` + `vTaskDelete`；`_connect_task` 由 join 端清空。

### 關鍵位置
- `companion_client.cpp`：`start`／`stop`／`connect_worker`／`connect_task_entry`

---

## F-05｜預設 Pi URL 與區網不符（設定債）

### 問題
韌體預設 `ws://192.168.1.1:8765/ws/device`；實機取得 IP 如 `192.168.50.27`，Pi 若不在 `192.168.1.1` 則永遠 timeout（屬預期失敗，不應當機）。

### 原因
Phase 1 佔位預設；尚未寫入實機 NVS／設定 UI。

### 解決方法（待做）
- 以 NVS 寫入正確 `pi_ws_url`／`pi_token`，或後續 Phase 提供設定頁。
- Namespace：`companion`；鍵：`pi_ws_url`、`pi_token`（一般 NVS，非 eFuse）。

---

## 驗證清單（修完後）

- [ ] 開 Companion：先 Wi-Fi Loading，不 panic 重啟  
- [ ] 連網後顯示臉；狀態／STOP 可見或可操作  
- [ ] Pi 不可達時：畫面仍可操作；連線中按 STOP 有 `stopAll: touch`  
- [ ] 底部上滑 → home → `on close` 後 warm reboot 回 Launcher，**無** StoreProhibited  
- [ ] Serial：**無**連續 `task_wdt: IDLE0`；允許單次 `connect failed`  
- [ ] 設定正確 Pi URL 後可看到 `CompanionWS connected`／hello  

## 燒錄／除錯注意

- 開 `idf.py monitor` 可能對 USB 下 RTS reset，裝置會重開，勿與「App 自己 crash」混淆。
- 燒錄前務必釋放 serial port（結束 monitor），否則 `Operation not permitted`。
- Banner `@build at` 可能未隨每次 flash 更新，以行為與 serial tag（`COMPANION`／`CompanionWS`）為準。

## 相關風險對照

| 本紀錄 | `14_RISKS_SPIKES.md` |
|---|---|
| F-01／F-03／F-04 | R-06 Wi-Fi、Pi 重啟／離線不得卡死 |
| F-02 | R-01 返回 Launcher；允許 warm reboot |
