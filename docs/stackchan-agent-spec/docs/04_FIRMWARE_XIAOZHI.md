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

## 4. 狀態仲裁矩陣

| 場景 | 通知 UI | 通知音效/TTS | Motion | 補送 |
|---|---|---|---|---|
| Coordinator ACTIVE＋Xiaozhi Idle＋政策有效 | 按等級允許 | 在音訊 lease 確認後允許 | Servo lease＋角度限制 | 可以 |
| Xiaozhi Listening/Speaking | 關閉或讓出 | 立即取消通知音訊，不能搶占原廠 | 讓出原廠動作控制 | 對話後重評估 |
| Coordinator 失聯／政策過期 | 清除所有 Agent 通知 | 停止並阻止任何通知音訊 | 安全停用通知動作 | 不可以，恢復 Gate 後重評估 |
| SD 資產故障 | 切內建角色 | 原廠音訊不受損 | 安全待機 | 與素材故障分離 |
| FreeRTOS 資源不足 | 減少動畫／省略音效 | 不阻塞 Xiaozhi | 降級安全姿態 | Coordinator 保留歷史 |

## 5. 原廠 Audio／TTS 共存（P0 未完成）

`hal_bridge::app_play_sound()` 的實作僅證明**播放已知 sound** 的入口；未證明可以安全播報任意文字。`Application::PlaySound`、音訊 service、PCM／Opus 處理與 Session ownership 需在拉取上游 `firmware/repos.json` 所指依賴後調查。**禁止以 `audio.cpp` 的麥克風測試（EnableInput/Output＋OutputData）當通知 TTS 捷徑**；那段測試可直接切換 Codec 狀態，可能破壞 Xiaozhi。

建議分三個能力層級：`A0=無通知音訊`（純 UI/Servo）；`A1=已驗證安全播放短提示音`；`A2=已驗證的文字 TTS／查詢整合`。每層獨立 Gate；語音查詢需使用原廠 Xiaozhi 安全可用的服務事件／工具回呼，未證實時標記 UNVERIFIED。不得透過額外付費 OpenAI API 作為預設方案。

## 6. Motion 安全

上游 `Motion::setModifyLock` 只是 bool，不是 Mutex；原廠 IMU Modifier 也會使用此旗標。通知 MotionAdapter 必須在提交前檢查 Arbiter、generation、可用角度與速度。`Motion::stop()` 將當前角度設成目標，**不代表已證明物理立即停止**。對 Yaw（可能有連續轉動模式）與 Pitch 分別測試。機構停止優先於回中心，避免突然碰撞；禁用任意外部指令直達 Servo。

## 7. Avatar／Mew

`StackChanAvatarDisplay::SetupUI` 建立 DefaultAvatar 與 Breath/Blink/HeadPet/IMU 等 Modifier。Mew Presenter 應可掛載完整身體圖層與通知狀態動畫，並保持原廠表情、睡眠、喚醒與觸控事件。若使用 `ShowNotification()`，需補全權限、時序、清除、ACK，不應直接把外部文字渲染到不受控視圖。SD 卡優先，素材驗證／解碼在低優先背景工作。欠缺 SD 時回內建角色，CoreS3 不留通知歷史。

## 8. 實機測試 Gate

必驗證：原廠 Xiaozhi 喚醒／對話／重進；多次同時 Agent 通知；Coordinator 突然斷線時清屏與音訊取消；Generation 舊回呼；LVGL Lock 占用時間；Servo 安全停止／搖晃 IMU；SD 缺失／損壞；PSRAM 峰值；看門狗；至少一次長時間穩定性執行，測試時長與合格線由 Phase 0 訂立。
