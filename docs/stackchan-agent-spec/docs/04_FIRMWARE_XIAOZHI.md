# 04｜CoreS3／Xiaozhi／FreeRTOS／LVGL／Motion 整合規格

## 1. 來源界限

已讀取的是 M5Stack 上游 `m5stack/StackChan` 的原始碼；個人分支 `jason22432150/StackChan` 讀取失敗，不能假設完全相同。上游可能落後於已發行的韌體。**以下以「上游可觀測」與「提案」區分。**

## 2. 上游已核對的整合點

| 路徑／函式 | 已證實行為（上游） | 建議 |
|---|---|---|
| `firmware/main/main.cpp::app_main` | 初始化 HAL、Mooncake Apps；切換 Xiaozhi 時卸載 Apps、DestroyMooncake，轉 `startXiaozhi()` | 通知不能只依賴 Mooncake App 生命週期 |
| `firmware/main/apps/app_ai_agent/app_ai_agent.cpp::onOpen` | 請求啟動 Xiaozhi | AI App 只是切換入口 |
| `firmware/main/hal/hal.cpp::Hal::startXiaozhi` | 建立 `stackchan` FreeRTOS 任務、設定 Reminder handler、啟動 Xiaozhi | 調查常駐控制器接入點，保留原廠服務 |
| `firmware/main/hal/hal.cpp::_stackchan_update_task` | 20ms 週期起步，LVGL guard，非 Idle 時有 100ms 延遲，更新 `GetStackChan()` | 不在持 UI 鎖時等待網路；量測鎖占用 |
| `firmware/main/hal/board/hal_bridge.h` | 有 Xiaozhi ready/idle、LVGL lock/unlock、`app_play_sound` | 可作薄適配層；Idle 不是音訊授權 |
| `firmware/main/hal/board/stackchan_display.cc::SetStatus` | 依 STANDBY/LISTENING/SPEAKING 更新 Avatar/Modifier 與 idle | 狀態機需使用可靠原廠對話事件，不只靠畫面狀態 |
| `...::ShowNotification` | **空實作** | 建立新的 NotificationPresenter，不能將空函式當可用通知 |
| `...::StackChanAvatarDisplay` | `esp_lvgl_port`、`LvglLock`、DefaultAvatar、Blink、Breath、HeadPet、IMU Modifier | 優先重用 LVGL 與 Avatar；需測試 Mew 衝突 |
| `firmware/main/stackchan/motion/motion.cpp` | move/goHome/stop；`setModifyLock` 僅寫 bool；move 不檢查此 bool | 不能用 ModifyLock 取代資源仲裁 Mutex |
| `firmware/main/stackchan/modifiers/imu.h` | IMU Modifier 會自行呼叫 `setModifyLock` 並復原 | 通知 Servo 不得忽略原廠 IMU 優先權 |
| `firmware/main/hal/board/hal_bridge.cc::app_play_sound` | 直接呼叫 `Application::PlaySound` | 有提示音介面；尚未證明 TTS 任意文字可用 |
| `firmware/main/hal/audio.cpp` | 硬體麥克風測試直接操作 AudioCodec 輸入／輸出 | **不可照抄作為通知 TTS**，會干擾原廠音訊 |

## 3. 建議軟體分層

`CoordinatorTransport`（連線、心跳、接收與回報）→ `NotificationController`（Fail-Closed、排程、TTL、Generation）→ `ResourceArbiter`（受控 UI／Audio／Motion Lease）→ `NotificationPresenter`、`AudioAdapter`、`MotionAdapter`。Xiaozhi 是資源優先層，不是 NotificationController 的子功能。裝置端只維持 RAM 暫態，保存必要裝置設定／配對憑證但不保存通知歷史。

### Task／執行緒約束

- Transport 網路回呼**不得**直接修改 LVGL、AudioCodec、Servo；應用有界 Queue 發送短命令與 generation。
- 保留原廠 `stackchan` 更新任務，先核對其 CPU 核心、堆疊、頻率與 Modifier 更新時序，避免無故複製高頻任務。
- LVGL 使用 `LvglLockGuard` 或實際原廠相容同步路徑；不要在持鎖期間做 SD 解碼、長網路等待或高延遲取消 ACK。
- 安全事件先同步撤銷授權／失效 Generation，再由 UI 執行者清理畫面，Audio/Motion 獨立取消，不等待全部子系統才停權。
- 所有非同步回呼於提交**可見**效果當下再次驗證 generation 及政策有效性，避免 time-of-check／time-of-use race。

### P0-04 執行期基準量測

- 本機 `Hal::startXiaozhi()` 將 `stackchan` task 固定在 core 1，優先級 3，stack 4,096 bytes。CoreS3 顯示的 LVGL port task 同樣在 core 1、優先級 3。現有 ESP32-S3 建置採 100 Hz FreeRTOS tick。
- `_stackchan_update_task` 每輪先延遲 20 ms、更新 Reminder，再建立 `LvglLockGuard`。Xiaozhi 非 Idle 時的 100 ms 延遲發生在 guard 內。更新 Avatar，以及 Ready 後的初始化和 UI 更新也在同一 guard 內。離開迴圈本體或執行 `continue` 都會析構 guard。底層顯示鎖最多等待 30 秒，失敗只會記錄 `Failed to lock display`，出現該錯誤的量測區間應判為無效。
- `StackChan Diagnostics` 的 `CONFIG_STACKCHAN_RUNTIME_BASELINE` 預設關閉。啟用後從序列日誌擷取 `StackChanBaseline`，約每五秒記錄更新週期、等鎖與持鎖時間的最大值。記憶體欄位包含內部 heap 與 PSRAM 可用量和最低可用量、PSRAM 最大連續可用區塊，以及 task stack 最低剩餘量。記錄在 guard 析構後執行。ESP-IDF 的 heap 最低可用量按區域追蹤，用來估計最壞餘裕。
- 實機需記錄板型、韌體 build ID 與情境，分別保留待機、喚醒／聆聽及回覆期間的樣本。這些樣本仍待取得，P2-04 的佇列容量與 lease 上界仍待決定。

## 4. 狀態仲裁矩陣

| 場景 | 通知 UI | 通知音效/TTS | Motion | 補送 |
|---|---|---|---|---|
| Coordinator ACTIVE＋Xiaozhi Idle＋政策有效 | 按等級允許 | 在音訊 lease 確認後允許 | Servo lease＋角度限制 | 可以 |
| Xiaozhi Listening/Speaking | 關閉或讓出 | 立即取消通知音訊，不能搶占原廠 | 讓出原廠動作控制 | 對話後重評估 |
| Coordinator 失聯／政策過期 | 清除所有 Agent 通知 | 停止並阻止任何通知音訊 | 安全停用通知動作 | 不可以，恢復 Gate 後重評估 |
| SD 資產故障 | 切內建角色 | 原廠音訊不受損 | 安全待機 | 與素材故障分離 |
| FreeRTOS 資源不足 | 減少動畫／省略音效 | 不阻塞 Xiaozhi | 降級安全姿態 | Coordinator 保留歷史 |

## 5. 原廠 Audio／TTS 共存（P0-03 本機基準）

基準為 StackChan `00af989` 與本機 Xiaozhi `v2.5.2`（`49b4380b3faa0ceadd28a3e78aaf0f311c46c57e`）加上 P0-02 驗證的既有 patch，對應 ESP32-S3 的本機建置。

| 路徑 | 本機原始碼與建置證據 |
|---|---|
| 既有短提示音 | `firmware/main/hal/hal.cpp` 的 Reminder handler 呼叫 `hal_bridge::app_play_sound(OGG_NEW_NOTIFICATION)`，由 `hal_bridge.cc` 轉給 `Application::PlaySound`。`audio/audio_service.cc::PlaySound` 將 Ogg Opus 封包送進共用解碼佇列，佇列滿時可等待。這個呼叫回傳 `void`，沒有個別取消或播放完成控制介面。 |
| Xiaozhi 對話 | `application.cc::InitializeProtocol` 的 `tts start/stop` 切換 Speaking 與 Listening／Idle。Speaking 時收到的音訊封包進入同一解碼佇列；`sentence_start` 的文字用於顯示。自動模式切回 Listening 時有等候播放排空的路徑，進入 Speaking 或啟用語音處理也可能重設解碼器。 |
| Xiaozhi 既有遠端通知 | Protocol 的 `notify` 需要 `audio_url`，字幕為選填。`Application` 在主迴圈從 Idle 啟動私有的 `StartNotification`，經 `NotifyPlayer` 下載 Ogg，進入 Notifying 並使用共用音訊服務。喚醒事件走 `StopNotification` 再開始對話，字幕及完成回呼受 `playback_id` 驗證。此介面接收已有音訊，Coordinator 的政策 lease 與任意文字 TTS 仍需獨立驗證。 |
| 取消邊界 | `AudioService::ResetDecoder` 增加播放 generation 並清空共用解碼、播放及測試佇列。已由 `AudioOutputTask` 取出的 PCM 仍可能進入 `OutputData`。這條路徑無法證明通知專屬取消或停止延遲，亦不應用於取消 Agent 通知時清除原廠對話。 |

**P0-03 結論**

- **A0（無 Agent 通知音訊）** 是目前採用的能力上限。後續 UI 或 Servo 各自依其驗收 Gate 啟用。
- **A1（短提示音）尚未驗證**。已確認內建 Ogg Opus 素材與播放入口存在。啟用前仍須驗證喚醒／聆聽／回覆的搶占、共享佇列排空、撤權停止上界與原廠對話回歸。Idle 訊號只能當作狀態輸入，派送仍須通過資源與政策授權。
- **A2（文字 TTS／語音查詢）尚未驗證**。已查到 Xiaozhi 對話播放與預先產生 Ogg 的通知路徑。Agent 文字合成、經授權的查詢及可獨立取消的呈現需要後續驗證。不得直接借用 `firmware/main/hal/audio.cpp` 的麥克風測試操作 Codec，或預設依賴額外付費 OpenAI API。

驗收使用本機 ESP32-S3 ELF 的符號表確認八個播放、取消與重設函式已連結，並驗證內建通知素材含 Ogg Opus 標頭（6,191 bytes）。全套 Python 回歸 150 項通過。CoreS3 音訊行為與停止時間仍待實機驗收。

## 6. Motion 安全

上游 `Motion::setModifyLock` 只是 bool，不是 Mutex；原廠 IMU Modifier 也會使用此旗標。通知 MotionAdapter 必須在提交前檢查 Arbiter、generation、可用角度與速度。`Motion::stop()` 將當前角度設成目標，**不代表已證明物理立即停止**。對 Yaw（可能有連續轉動模式）與 Pitch 分別測試。機構停止優先於回中心，避免突然碰撞；禁用任意外部指令直達 Servo。

## 7. Avatar／Mew

`StackChanAvatarDisplay::SetupUI` 建立 DefaultAvatar 與 Breath/Blink/HeadPet/IMU 等 Modifier。Mew Presenter 應可掛載完整身體圖層與通知狀態動畫，並保持原廠表情、睡眠、喚醒與觸控事件。若使用 `ShowNotification()`，需補全權限、時序、清除、ACK，不應直接把外部文字渲染到不受控視圖。SD 卡優先，素材驗證／解碼在低優先背景工作。欠缺 SD 時回內建角色，CoreS3 不留通知歷史。

## 8. 實機測試 Gate

必驗證：原廠 Xiaozhi 喚醒／對話／重進；多次同時 Agent 通知；Coordinator 突然斷線時清屏與音訊取消；Generation 舊回呼；LVGL Lock 占用時間；Servo 安全停止／搖晃 IMU；SD 缺失／損壞；PSRAM 峰值；看門狗；至少一次長時間穩定性執行，測試時長與合格線由 Phase 0 訂立。
