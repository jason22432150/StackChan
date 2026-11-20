# 04｜原廠韌體整合計畫（保留舊入口）

## 已確認的源碼基礎
- `firmware/main/main.cpp` 安裝 Mooncake Apps；原廠 AI 觸發後會退出 Mooncake 更新迴圈、卸載 Apps，最後進入 `startXiaozhi()`。
- `firmware/main/apps/app_ai_agent/app_ai_agent.cpp` 的 `onOpen()` 呼叫 `requestXiaozhiStart()`；**本專案不刪除此路徑**。
- `firmware/main/apps/app_template/app_template.cpp` 有 App 生命週期和 `LvglLockGuard` 範例。
- `firmware/main/hal/audio.cpp` 透過 `Board::GetInstance().GetAudioCodec()` 做既有麥克風／喇叭測試路徑。
- `firmware/main/hal/hal_ws_avatar.cpp` 已存在 Opus、文字、馬達的 WebSocket 訊息概念，但它**不是本案現成可用的 Pi 協定**。
- `firmware/main/stackchan/modifiers/idle_motion.h` 有避免馬達正在移動時堆疊操作的範例。
- `firmware/main/CMakeLists.txt` 以 `GLOB_RECURSE apps/*.cpp` 蒐集源碼，新增 `.cpp` 通常被涵蓋，但需檢查 build 與新增依賴。

## 新增與最小改動
| 位置 | 工作 |
|---|---|
| `firmware/main/apps/app_companion/` | 新增 App、UI、配對、網路、音訊適配器、可用動畫表 |
| `firmware/main/apps/apps.h` | include 新 App |
| `firmware/main/main.cpp` | 註冊 App，新增安全的 Companion 開機選擇流程；保留原廠 Xiaozhi 啟動路徑 |
| `firmware/main/apps/app_setup/` | 視現有設定框架加開機模式與喚醒詞開關（先以最小改動實作） |
| `firmware/main/stackchan/` | 僅在需要新動畫／表情時擴充；避免大改既有動作核心 |

## Companion App 生命週期
- `onCreate`: 設定 App name、icon、預設狀態。
- `onOpen`: 建 UI、連 Pi、取得 Companion 對麥克風/喇叭的控制權。
- `onRunning`: 處理有界事件佇列，更新文字、表情、動畫；**不可同步等待雲端 API**。
- `onClose`: 即刻停音、停止轉頭、解除喚醒偵測、關閉 socket、釋放 UI/音訊，再交回 Launcher。

## 喚醒與觸控打斷
- **MVP 包含觸控與喚醒詞**。先做音訊能力/CPU/記憶體探測，選「設備端輕量喚醒」或「Pi 端喚醒引擎」；兩條路線均須能在 Companion 閒置模式觸發收音。
- 播音階段不做語音打斷，避免自己的喇叭觸發喚醒；保留觸控取消，播放元件先立即停止，再送取消訊息。
- `onClose` 與 Pi 離線情境都要確保麥克風沒有殘留錄音任務。

## 動畫、字幕、馬達安全
- 本機 LVGL 渲染和動畫執行，不靠 Pi 逐幀傳指令；不可在 socket callback 直接操作 LVGL，透過 `LvglLockGuard`。
- `idle/sleep/read/work/eat/walk` 若無素材，先製作簡單可辨識的 LVGL 動畫/字幕替代，不能宣稱原廠已有相同動畫。
- 用單一馬達 owner 做動作決策；保守角度、速度、冷卻時間；收到 `STOP` 立即停止。**模型只能選已定義動作，不可設定任意硬體參數。**

## Companion 優先／原廠共存
- 啟動選項儲存在一般 NVS：`boot_mode=companion|launcher`；完成可靠開關與失敗退回測試後，使用者可將 Companion 設為預設。
- Pi 離線≠裝置啟動失敗：可顯示離線待機、返回 Launcher，禁止無限重啟。
- 原廠 Xiaozhi 仍由原有 App 啟動；其返回 Launcher 的實際機制需實機驗證，不得假設無縫切換。
- 原廠模式期間**禁止顯示任何 Companion Agent 通知**；只在 Companion App 活動且資源由它持有時可通知。

## 禁止事項
- 禁止刪除原廠 `app_ai_agent`，或把 `main.cpp` 改成唯一的 Companion 主程式。
- 禁止新增任何 eFuse 寫入、Secure Boot/Flash Encryption provisioning、破壞原廠 OTA 分割區。
- 不需要 StackChan microSD；第二張 128GB 暫留。

## 原廠設定新增 Storage / microSD（v2.3.1）
- 已確認 `app_setup/app_setup.cpp` 的 `Device` 分組是新增入口的最低改動位置：增加 `Storage / microSD`，採既有 Worker 選單/返回模式。
- 新增 `workers/storage.cpp`、`SdCardStatusWorker` 與 `hal_storage.cpp` 或同等輕量 storage module，獨立提供狀態、容量查詢。
- 必須檢查 SPI bus 共用方式及 Card Detect 是否存在，不能假設 Arduino 範例直接等於 ESP-IDF 原廠韌體實作。
- UI thread 不做阻塞式 mount / FATFS 容量掃描；使用背景工作結果更新 LVGL。
- 唯讀、`format_if_mount_failed=false`、不新增任何 eFuse 寫入、不得自動修改 SD 內容。詳細見 `11_SD_STATUS_SETTINGS.md`。

## v2.3.3 新增的 StackChan 本機責任
- **新增 Companion App，但不是獨立可安裝 binary**：原廠 Mooncake App 是一起編進韌體的，首次加入需要重新 build/flash；Pi AI 更新不必每次刷機。
- **本地 Activity Executor**：至少可播放 `idle/read/work/eat/sleep/walk/explore/create` 的基本可辨識表現；接受 Pi 高階行為指令後自行管理眨眼、翻頁、輕度動畫，不需要逐幀走網路。
- **Stop 優先**：觸控中止時先停止本機 TTS 輸出，再通知 Pi 取消；即使 Pi 正在斷線仍能停止本機播放。
- **離線模式**：當 Pi 無法連線時顯示狀態並執行有限的本機待機動畫；不假裝雲端 AI 已回答。
- **不打擾**：所有主動文字泡泡和主動語音在切出 Companion 前先取消；原廠 App 不注入 Companion overlay。
- **資源與執行緒安全**：LVGL 更新須依既有 `LvglLockGuard` 慣例；音訊與網路不能阻塞 `onRunning()`；避免重複初始化音訊 Codec 或與原廠爭用。
- **韌體權限**：即便 Pi 送來過界的動作，裝置仍必須限位與拒絕；不得接受 LLM 原文作為硬體指令。

### 已驗證來源及尚未驗證區分
已確認：`main.cpp` 中 Xiaozhi 進入後卸載 Apps；`app_template` 有四種生命週期；`hal/audio.cpp` 有音訊讀寫測試；`hal_ws_avatar.cpp` 含 Opus／文字／動作訊息種類；`app_setup.cpp` 有 Worker 選單。**尚未驗證**：可供 Companion 重用的串流 Opus 流水線、喚醒詞是否可本機常駐、ESP32-S3 可用堆記憶體、連續語音與場景動畫的並行性能。
