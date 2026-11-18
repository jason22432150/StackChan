# 04｜CoreS3／Xiaozhi／FreeRTOS／LVGL／Motion 整合規格

## 1. 來源界限

### P0-01 Git 基準（2026-11-16）

| 來源 | 核對的分支與 HEAD |
|---|---|
| [M5Stack 上游](https://github.com/m5stack/StackChan/tree/28b9f0c8bd6acd81cb3c70f1a93c3e373b39d400) | `main`／`28b9f0c8bd6acd81cb3c70f1a93c3e373b39d400` |
| [使用者 fork](https://github.com/jason22432150/StackChan/tree/4a39d5114c5d8ea555444396434918db6a0f5656) | 預設分支 `my-stackchan-01`／`4a39d5114c5d8ea555444396434918db6a0f5656` |
| 本機 checkout | `feature/agent-notifications`／`f7f11f4168bc95a6d170d48e456b07711c086592` |

`git ls-remote --symref` 回傳的兩個遠端 HEAD 與本機基準 ref 相同。遠端 fork 在此次查詢未列出 `feature/agent-notifications`。以「落後／領先」表示，fork 對原廠基準為 0／3，本機對 fork 為 0／13，本機對原廠基準為 0／16。兩個基準都是本機 HEAD 的祖先。

相對原廠基準，本機 `firmware/` 的七個差異檔案中，會進入韌體建置的差異集中在 `main/Kconfig.projbuild` 與 `main/hal/hal.cpp` 的 P0-04 診斷。依賴清單、lockfile 與 patch 的指定路徑差異檢查通過。版本對照使用原始碼 commit，出廠映像的對應版本仍待實機確認。

本輪授權涵蓋本機開發、測試與提交上一輪結果。推送、合併主分支、燒錄與 OTA 均未執行。G0 整體驗收仍依 `07_TEST_ACCEPTANCE.md` 的其餘證據判定。

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

P2-05 已落地獨立 `ResourceArbiter`（`resource_arbiter.h／.cpp`）：以 Generation Token 授權 UI／Audio／Motion 租約；`mayCommit`／`resourceArbiterCommitGate` 是可見效果提交閘門（T-SEC-03）；`cancelCurrent`／`revokeAll` 同步撤銷並立即回傳取消確認，不等待子系統 ACK；`onXiaozhiActivity(Busy)` 立即撤銷通知 Audio／Motion 並讓出 UI，Idle 後同一 Generation 可重取。host CTest 覆蓋上述行為；`link_anchor` 保留 `resourceArbiterCommitGate` 符號且不啟動執行期路徑。

P2-06 已落地 `NotificationPresenter`＋`LvglLockedUiPort`＋`makeHalLvglLockHooks`：中性／成功通知必須經 UI 租約與 mayCommit；所有 show／clear 走與 `LvglLockGuard` 相同的 Hal LVGL lock；Xiaozhi Busy 拒絕 present 並清屏。`ShowNotification()` 仍為空實作，尚未掛入 `StackChanAvatarDisplay`（避免未授權改動原廠顯示路徑）。

P2-07 已落地 `PresentationReceiptTracker`＋`encodePresentationReceiptJson`：裝置端產生 accepted／started／completed／interrupted／cancelled／failed 收據；相同 receipt_id 轉移與 Coordinator 多次 ACK 冪等；compact JSON 對齊 `presentation-receipt.schema.json`（金樣契約測試）。`link_anchor` 保留編碼進入點且不啟動網路／UI。尚未由 Presenter 驅動或經 HTTP／stream 上報。

P2-08 軟路徑已落地 `FailClosedGuard`：偵測 Controller Active／Recovering→Suspended（心跳逾時）或 transport 顯式斷線時，同步 `Presenter.interrupt`、可選 `interrupted` 收據與清屏；不觸及 Xiaozhi。host CTest 覆蓋 T-SEC-01 軟行為。R-006 軟體預算見 `fail_closed_budget`（4185 ms）；CoreS3 實機 Gate G3 與 R-006 實機量測仍未關閉。

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
- 2026-11-16 在 CoreS3（ESP32-S3 rev v0.2、8 MiB PSRAM、Windows COM8）以 `f7f11f4` 診斷版量測，ELF SHA256 為 `9477d38f820f2427532177d622c273ee5a6724b269f103e84271d4aa4864b37c`。序列紀錄共 41 個約五秒視窗，包含 Idle → Connecting → Listening → Speaking → Listening → Idle。下表僅計入能明確歸於單一狀態的視窗。

| 狀態 | 樣本數 | 最大更新間隔 (µs) | 最大等鎖 (µs) | 最大持鎖 (µs) | 最低取樣可用內部 heap (bytes) | 最低取樣可用 PSRAM (bytes) |
|---|---:|---:|---:|---:|---:|---:|
| 待機 | 17 | 44,649 | 6,136 | 13,787 | 18,875 | 7,577,972 |
| 聆聽 | 6 | 141,222 | 9,687 | 108,835 | 14,923 | 7,577,620 |
| 回覆 | 5 | 184,054 | 45,297 | 116,819 | 13,639 | 7,569,864 |

納入轉換視窗時，最大持鎖為 117,429 µs。裝置回報內部 heap 低水位 5,424 bytes、PSRAM 低水位 7,555,464 bytes，task stack 低水位 1,592 bytes。擷取期間未記錄顯示鎖逾時。這組數據是單次工作負載的實測基準。

P2-04 MVP 正式預設（`kCoreS3MvpRuntimeProfile`／Coordinator `CORE_S3_MVP_RUNTIME_LIMITS`）：佇列容量 4、心跳逾時 4,000 ms、穩定門檻 5,000 ms、封包年齡 5,000 ms、影格 1,024 bytes、網路逾時 10,000 ms。選定理由：容量等於硬上限且只存 delivery ID；心跳／穩定對齊 Coordinator；心跳逾時約為最差 UI 更新間隔（184 ms）的 21 倍。`sanitizeRuntimeProfile` 拒絕超出硬天花板的設定。R-006：軟體上界 `kMvpSoftWorstCaseRevokeMs=4185`；CoreS3 診斷 probe 實測 `revoke_ms=4000`（`interrupted=true`／`within_budget=true`，見 `docs/evidence/r006_device_revoke_measure.md`）。生產韌體預設關閉 `CONFIG_STACKCHAN_R006_REVOKE_PROBE`。

P2-04 產品路徑主迴圈：`NotificationProductLoop`（FailClosed→takeNext→present）＋`NotificationProductRuntime`（Null UI、不自動 start TLS）。掛點：`CONFIG_STACKCHAN_AGENT_NOTIFICATIONS`（default n）於 `_stackchan_update_task` 在 LVGL lock **外**呼叫 `tickNotificationProductRuntime`（含 Xiaozhi Busy／Idle 轉發）。host CTest `notification_product_loop_test`／`notification_product_loop_poll_test` 覆蓋 Idle／Present／Fail-Closed／Busy 拒呈／未 start TLS。

P2-04 憑證／arm：`armProvisionedDeviceStream`＋`fetchAndArmDeviceStream`；runtime `armNotificationProductRuntime`／`isNotificationProductStreamArmed`（未 init／已 started／無效 provision Fail-Closed）。host `start_provisioned_stream_test` 覆蓋雙重 arm、fetchAndArm 101／401。`idf.py build`：`armProvisionedDeviceStream`／`fetchAndArmDeviceStream` live；`stack-chan.bin` 0x39ed40、partition 剩 27%、SHA256 D8D568EA…029BDCB4。未寫入 NVS 密鑰、未自動 fetch。Avatar／實機 Coordinator 仍缺——P2-04 不勾完成。

`loadNotificationCredentials` 在啟用 `CONFIG_NVS_ENCRYPTION` 時以唯讀方式開啟已初始化的預設 NVS 命名空間 `agent_notify`。`port` 為非零 u16，`host`、`device_id`、`token`、`ca_pem` 為字串，上限依序為 253、128、512、3,999 bytes。讀取出錯或任一欄位無效即回傳無憑證。PEM 僅檢查文字邊界，信任鏈及主機名由後續 TLS 握手驗證。此 NVS 載入器為先前驗證路徑。產品 runtime 從本機配對流程接收 RAM 憑證。beginNotificationProductPairing 記錄本機啟動且已從可信 Coordinator 取得的有效 challenge 與端點。finishNotificationProductPairing 核對同一配對的緊湊 JSON 完成回應、device 類型、通知 scope 與憑證期限後，才交付 RAM 暫存。完成回應只處理一次。拒絕、過期或重啟後無有效 challenge 時不交付憑證。產品端由呼叫端明確呼叫 `fetchAndArmNotificationProductRuntime`，傳入 Coordinator 的 generation。入口先檢查 runtime 已初始化、尚未連線，且本次開機已收到既有 SNTP 同步回呼。只有 RTC 或正值的系統時鐘時，入口不讀憑證也不連線。同步確認在同一次開機保留。通過檢查後，入口取樣系統 UTC 毫秒、一次取用 RAM 憑證，再透過 TLS 取得 policy。若在 GET 期間到期，停止升級。成功升級的串流以憑證及 policy 兩者中較早的期限停權。通知 tick 使用同一個 UTC 毫秒來源。初始化與閒置 tick 不會讀取憑證或發起連線。本機操作透過 `requestNotificationProductStream(generation)` 接入。只有啟用通知功能、時鐘已同步且沒有執行中的任務時才接受。FreeRTOS 專用任務依序初始化、握手與輪詢，斷線或啟動失敗即退出，下一次連線需重新請求。顯示更新迴圈只傳遞 Xiaozhi 忙碌狀態。專用任務暫採 8 KiB stack，實機須量測剩餘 stack 與內部 heap。啟用通知的建置在 SETUP → Agent Notifications 提供 Connect notifications。需在建置設定 `STACKCHAN_AGENT_COORDINATOR_GENERATION` 填入與 Coordinator 相符的 1 到 20 位十進位數字（uint64）。開啟頁面不會連線，只有點選才送出請求。提示只回報請求已送出或遭拒。NotificationPairingClient 使用已信任的 Coordinator 主機及 CA，分開指定配對與通知串流連接埠。start 透過 HTTPS 取得 challenge，僅把確認碼交給呼叫端，領取碼留在記憶體。complete 將同筆配對的領取碼送回 Coordinator，成功才把回應交給既有 RAM 暫存入口。配對與 policy GET 共用有界的 HTTP Content-Length 驗證。requestNotificationProductPairing 提供非阻塞本機入口，由與通知串流共用的獨占任務執行 start、每秒檢查核准，以及成功後的政策取得與串流啟動。notificationProductPairingStatus 提供階段與六位確認碼，其他憑證只留在任務內。取消適用於進入 Connecting 之前，進行中的 HTTPS 完成後處理取消；若此時剛取得憑證，先丟棄待用憑證再退出。確認碼在失敗、取消或離開待核准階段時清除。SETUP UI、與真實 Coordinator 的整合及實機點選仍待驗收。

P2-04 產品與實機驗收沿用預設 NVS 的既有分割表、資料格式與原廠初始化行為。通知功能不依賴 eFuse 寫入，也不在預設 NVS 持久保存通知 token。後續由本機明確配對取得短效通知憑證，裝置端只保存在 RAM。缺少憑證、到期或重啟後須重新取得有效憑證才能發起通知連線。RAM 佈建與生命週期仍待實作及驗收。

加密 NVS 建置保留作為先前的離線連結證據。該設定下，HAL 啟動先向 ESP-IDF 已註冊的預設 provider 讀取既有金鑰。讀取成功才呼叫 `nvs_flash_secure_init`，返回前清除暫存金鑰。金鑰缺失、讀取錯誤或初始化失敗時回報原錯誤並停止啟動。未加密建置沿用既有的自動復原。

燒錄前可用 `firmware/verify_nvs_backup.py` 離線比對兩份獨立擷取的原始 NVS 備份。工具依裝置對應的 CSV 分割表核對長度，拒絕全零／全擦除樣本與同一檔案的別名，並回報 offset、大小和 SHA-256。可用 `--binary-partition-table` 指定實際擷取的分割表，接受 0xC00 bytes 的表或 0x1000 bytes 的完整 sector。工具核對表內 MD5 與 NVS 範圍，搭配 `--show-partition` 可在取得 NVS 備份前查出 offset 與大小。若使用 CSV，可用 `--partition-table` 指定與裝置相符的表。[ESP-IDF 分割表格式](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/partition-tables.html)。備份可能包含配對或 Wi-Fi 資料，應保存在受保護的位置。相同摘要只能證明輸入一致，分割表來源、裝置身分、金鑰狀態與可回復性仍須另外確認。

取得批准並將 CoreS3 手動切到 ROM download mode 後，可從 repo 根目錄用 ESP-IDF Python 執行 `python -m firmware.capture_nvs_backup`。指定已確認的 `--port`、`--table-offset`，以及版本庫之外的私人 `--output-parent`。工具先讀一個分割表 sector，驗證後再按表內範圍讀兩次 NVS。它只呼叫 esptool `read-flash`，禁止自動重啟與上傳 flasher stub。若讀取或比對失敗，只清理本次新建的本機暫存檔。成功時保留分割表與兩份備份。裝置維持 ROM mode，恢復正常運作仍須操作員退出 bootloader。實機擷取與重啟的證據見開發清單 P2-04，回復待驗收。[esptool 重設選項](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/esptool/advanced-options.html)

回復前可執行 `python -m firmware.verify_nvs_backup --binary-partition-table captured-sector.bin --target-binary-partition-table target-partition-table.bin capture-1.bin capture-2.bin`。工具核對兩份二進位分割表的 MD5 與 NVS 範圍，再確認兩份備份內容相符。離線結果只涵蓋分割區 offset、大小及備份一致性。裝置身分、加密與金鑰狀態，以及實際回復仍須另行驗證。

實機量測可在驗收映像同時啟用 `STACKCHAN_RUNTIME_BASELINE` 與通知功能。通知 task 在 `bootstrap_failed`、`upgraded`、`disconnected` 記錄 `AGENT_NOTIFY_RESOURCE`，欄位包含本次 task 的 stack 最小餘量、當前內部 heap、開機以來內部 heap 低水位與當前最大連續區塊，單位均為 bytes。可對照既有 `StackChanBaseline` 的顯示更新與 LVGL 持鎖間隔。同一行的 `bootstrap_result` 使用固定代碼，區分 runtime 未初始化、串流已開啟、時鐘未同步、憑證不可用、政策取得或驗證失敗，以及串流啟用失敗。紀錄不含憑證、policy 內容或 TLS 診斷明細。若 task 未能建立，該 task 不會產生資源紀錄。

在 ESP-IDF 6.1 環境下，從 `firmware` 目錄建置 P2-04 離線驗收映像。使用新的建置目錄，讓 Kconfig 從兩份 defaults 產生獨立的 `sdkconfig`。如果已有 `sdkconfig.defaults.local`，應在沒有該本機覆寫檔的 checkout 執行，因為 CMake 會優先使用它。

```powershell
$buildDir = Join-Path $PWD 'build/p204-notifications'
$sdkconfigPath = Join-Path $buildDir 'sdkconfig'
idf.py -B $buildDir -D "SDKCONFIG=$sdkconfigPath" -D 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.p204-notifications' reconfigure build
```

此設定啟用 SETUP 的通知連線入口及資源診斷，測試用 Coordinator generation 設為 `1`。沿用預設分割表及未加密 NVS 設定，缺少 RAM 憑證時會 Fail-Closed。這組映像已用於驗證編譯、連結與分割區容量。正向連線驗收需完成短效 RAM 憑證佈建。

`reconfigure` 會重新收集 SETUP worker 原始碼並從實際 Kconfig 產生新增配對設定，避免沿用舊建置清單。已備妥鎖定依賴時，可在目前 PowerShell 設定 `$env:IDF_COMPONENT_CHECK_NEW_VERSION='0'` 關閉非必要的新版本檢查；這不變更 `dependencies.lock`，也不保證 Component Manager 完全不連線。

2026-11-18，上一輪配對頁面提交 `8591f15` 後，以 ESP-IDF 6.1 重新生成設定並完成 ESP32-S3 全映像建置（2,414 步）。未補入建置設定替身；實際 `sdkconfig` 的通知與 baseline 均為啟用、generation `1`、配對／串流埠分別為 `9443`／`8443`、host 與 CA 空白，NVS 加密、Flash Encryption 與 Secure Boot 均關閉。`compile_commands.json` 包含配對頁面、HTTPS client、共用 HTTPS 及通知 task；最終 ELF 的定義符號涵蓋 `NotificationPairingWorker`、`NotificationPairingClient`、`requestNotificationProductPairing`、`notificationProductPairingStatus`、`beginNotificationProductPairing`、`finishNotificationProductPairing`、`Application::Run` 與 `AudioService::Start`。

`esptool image-info` 的 checksum／validation hash 有效；`stack-chan.bin` 大小 `0x3a6ee0`（3,829,472 bytes），最小 app 分割區 `0x4f0000`，餘 `0x149120`（26%）；SHA-256 `266C00B6877E78E7F69E71F15C67C56D4F5836A7968EDD0954AF3074C310BB7D`。二進位分割表與本機基準逐位元組相同，SHA-256 `48DA0866F56D9D8EB1FE786412984D8F1A4A01B3F13F965621FCB916761E1A4B`；離線 MD5／範圍檢查通過，NVS 仍為 `0x9000`／`0x4000`。Host CTest 31/31、全套 pytest 285/285 通過；上一輪頁面與通知任務專項另重跑 4/4 通過。

首次建置因 GitHub 依賴檢查失敗；關閉新版本檢查後，Component Manager 在 registry 不可達時沿用既有鎖定的 64 筆依賴，lockfile 無變更。建置仍有既有元件的 Kconfig 值、私有標頭引用與未使用變數警告，未於本輪擴大修改。上述僅證明離線編譯、連結、映像完整性及分割配置；未燒錄、開啟 LAN listener、寫入 NVS 或 eFuse。空白 host／CA 不具正向配對條件。實機觸控、SNTP、CoreS3 HTTPS、重新開機後重新配對、TLS 與 task 的 heap／stack 用量，以及配對期間 Xiaozhi 喚醒／對話共存仍待驗收。

要驗證加密 NVS 的完整編譯與連結，可在同一 ESP-IDF 環境用第三份 defaults 建置至另一個目錄。此設定將 ESP32-S3 的 HMAC provider 與通知路徑連結至同一映像。金鑰 ID `0` 是建置測試輸入，實機的金鑰槽、既有 NVS 資料及回復方案須另行確認。

```powershell
$buildDir = Join-Path $PWD 'build/p204-nvs-linkcheck'
$sdkconfigPath = Join-Path $buildDir 'sdkconfig'
idf.py -B $buildDir -D "SDKCONFIG=$sdkconfigPath" -D 'SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.p204-notifications;sdkconfig.defaults.p204-nvs-linkcheck' build
```

此映像僅供離線檢查。即使分割表與未加密映像相同，啟用 NVS 加密也會改變預設 NVS 的資料解讀方式。硬體驗收須先確認備份可回復、指定的 eFuse 金鑰用途是 `HMAC_UP`，且預設 NVS 資料與該金鑰衍生的加密設定相容。

使用 `firmware.verify_nvs_efuse` 可離線核對已取得的 ESP32-S3 eFuse 摘要。摘要只需映像所設定金鑰 ID 對應的 `KEY_PURPOSE_<ID>`、`RD_DIS` 與 `WR_DIS`。工具檢查用途為 `HMAC_UP`，且金鑰槽設有讀取與寫入保護。檢查結果限於摘要中的中繼資料。摘要來源、裝置身分、金鑰能否使用及 NVS 能否回復仍須另外驗證。

從 repo 根目錄可用 ESP-IDF 的 Python 重現虛擬空白槽驗證。預期檢查器回傳 `1`，表示不符合條件。符合條件回傳 `0`，摘要無效回傳 `2`。

```powershell
$report = Join-Path $env:TEMP 'p204-efuse-virtual.json'
$output = python -m espefuse --chip esp32s3 --virt summary --format json KEY_PURPOSE_0 RD_DIS WR_DIS
if ($LASTEXITCODE -ne 0) { throw 'espefuse summary failed' }
$summary = $output -join "`n"
$start = $summary.IndexOf('{')
if ($start -lt 0) { throw 'JSON summary missing' }
[IO.File]::WriteAllText($report, $summary.Substring($start))
python -m firmware.verify_nvs_efuse $report --sdkconfig firmware/build/p204-nvs-linkcheck/sdkconfig
```

`--sdkconfig` 會從目標映像的建置設定取得金鑰槽。摘要須包含該槽對應的 `KEY_PURPOSE_<ID>`。若單獨檢查指定槽位，可改用 `--key-id`。

SETUP → Agent Notifications → Pair notifications 提供本機配對頁面。開啟頁面後，使用者按 Start pairing 才送出背景請求。待核准時顯示六位確認碼，並可按 Cancel and back 返回。頁面關閉或返回會取消由該頁面發起且仍在待核准階段的請求，進入連線階段後可離開頁面繼續使用通知。失敗、取消或斷線後可重新開始配對。

配對頁面使用建置設定 `STACKCHAN_AGENT_COORDINATOR_HOST`、`STACKCHAN_AGENT_PAIRING_PORT`、`STACKCHAN_AGENT_STREAM_PORT`、`STACKCHAN_AGENT_COORDINATOR_CA_PEM` 與既有 generation。主機與 CA 預設空白，須填入受信任的 Coordinator 設定才能配對。CA 欄位可用字面上的 `\n` 表示 PEM 換行。兩個連接埠預設分別為 9443 與 8443，可依 listener 設定調整。配對請求只進入背景任務，頁面 update 在既有 LVGL lock 下讀取狀態及更新元件。完整映像已於上述離線建置驗證，實機顯示與觸控操作仍待驗收。

### P2-04 隔離測試環境（2026-11-18）

使用者授權建立本機隔離測試環境，檔案位於 `firmware/build/p204-bench-private/`；新資料夾已移除繼承 ACL，僅本機使用者及 SYSTEM 具完整存取權。`git check-ignore` 確認憑證、私鑰、資料庫、環境設定及建置設定均不納入 Git。檔案包含 `ca.pem`／`ca-key.pem`、`server.pem`／`server-key.pem`、`security.sqlite`、`credentials.json`、`env.ps1`、兩份啟動腳本、`sdkconfig.defaults` 及不含機密的 `validation.json`。不可將整個目錄附到 issue、PR 或診斷匯出。

本輪網卡唯讀盤點顯示 Coordinator Wi-Fi 為 `10.12.245.137/24`，目標 CoreS3 為使用者提供的 `10.12.245.29`。測試伺服器憑證包含 `10.12.245.137` 與 `127.0.0.1`；以 SSL MemoryBIO 完成兩個名稱的 CA／金鑰／主機名驗證，未連線 LAN。測試管理員僅具 `admin:pairing`；政策為 `p204-bench`／`v1`／private，管理員 grant 與政策均於 `2026-11-18T14:22:52Z`（台北 22:22:52）到期。到期後不能沿用本次正向驗收條件，須明確重新準備測試授權與政策。

已使用這組實際檔案的受保護資料庫副本，在真實 loopback TLS 驗證 synthetic device 的 start → 人工確認 CLI → complete → policy GET → WebSocket heartbeat（generation 1）。原始測試資料庫保持乾淨。此證據是本機服務驗證，並不代表 CoreS3 配對成功。

通知映像建置目錄為 `firmware/build/p204-bench/`，使用既有 defaults、通知診斷 profile 與隔離目錄的第三份 defaults；不修改產品預設設定。第三份設定指定 Coordinator `10.12.245.137`、配對埠 9443、串流埠 8443 及本次 CA。產生 Kconfig 字串時，須先將 PEM 換行改為字面反斜線 n，再作字串跳脫；單層跳脫會被 Kconfig 讀成字母 n。本輪曾因此停止首次建置並修正。重新產生後，已確認 SDKCONFIG 的 CA 經產品使用的換行解碼後與原始 CA 逐字相同，且可載入為可信 PEM。通知／baseline 啟用，generation 1；NVS 加密、Flash Encryption 與 Secure Boot 關閉。

`start-pairing.ps1` 與 `start-stream.ps1` 已完成 PowerShell 語法檢查，尚未執行。準備的 LAN 範圍是 `10.12.245.137:9443`（配對）及 `:8443`（policy／stream），均只接受裝置來源 `10.12.245.29`；管理員確認固定 `127.0.0.1:9444`。腳本以個別前景程序執行，結束時各按 Ctrl+C；不建立背景服務或防火牆規則。此處僅記錄可供審查的設定，尚未授權／驗證實際 LAN 綁定、CoreS3 流程或燒錄。實機前須重新確認位址、授權期限與未占用連接埠；燒錄的分割區及回復方式需另外確認，不因建立測試環境而取得寫入裝置授權。

ESP-IDF 6.1 隔離映像完整建置 2,529 步通過；`stack-chan.bin` 為 `0x3a71a0`（3,830,176 bytes），最小 app 分割區剩 `0x148e60`（26%），SHA-256 `1F1DA41ACFBA43A6CC8CD45C4BC77AB15AA4E9B66E626A992BD4B695E0105D27`。esptool checksum／validation hash 有效；ELF 的配對頁面、client、請求／狀態、begin／finish 及 Xiaozhi `Application::Run`／`AudioService::Start` 八項符號檢查通過。映像包含預期的公開 CA 與 host，不包含本輪產生的兩份私鑰、pepper 或管理員 token。二進位分割表與先前通知映像逐位元組一致（SHA-256 `48DA0866F56D9D8EB1FE786412984D8F1A4A01B3F13F965621FCB916761E1A4B`），離線檢查 NVS 仍為 `0x9000`／`0x4000`。

本輪未修改產品程式碼、依賴清單或 lockfile。Xiaozhi HEAD 仍為 `49b4380b3faa0ceadd28a3e78aaf0f311c46c57e`，其追蹤檔差異經暫存 index 套用比對，完全等於既有 `xiaozhi-esp32.patch`。全套 pytest 362/362、host CTest 31/31 重驗通過。既有元件的 Kconfig、私有 include 與未使用變數警告仍存在，不宣稱零警告；實際 CoreS3 配對、SNTP、task heap／stack、重啟及 Xiaozhi 共存均未驗收，P2-04 保留未完成。

後續獲准的 LAN 驗證發現 Windows 已保留 8443；經使用者同意，隔離測試的串流埠改為 **9445**，配對 9443、管理 9444 不變。`p204-bench-private/sdkconfig.defaults` 與 `start-stream.ps1` 已同步更新；原 `p204-bench/` 的 8443 映像保留為歷史產物，不能用它搭配目前的 9445 服務。新版建置使用另一目錄 `firmware/build/p204-bench-9445/`，與產品預設設定分開。真實網卡 bind、TLS 與來源限制的 17 項驗證及範圍限制見 03 文件與 `evidence/p204_lan_bind_20261118.json`；全部 listener 已關閉，未改防火牆。

操作員接上 USB 後，唯讀列舉顯示 `COM8`、VID/PID `303A:1001`。本輪未開啟序列埠、進入 ROM、重新讀取晶片 MAC／分割表、重啟或寫入裝置；USB 列舉不等同本輪已驗證 flash 內容或裝置端配對。後續仍須確認裝置身分、目前分割表與可回復備份，再另行確認燒錄範圍。

9445 新映像已完成 ESP-IDF 6.1 全量建置（2,529 步），`p204-bench-9445/stack-chan.bin` 為 `0x3a71a0`（3,830,176 bytes），最小 app 分割區剩 26%，SHA-256 `9440C93901EDED259792F6FFE7CA8BBC949BAFAA5B0013CDD25A4BD98D8CA92B`。esptool checksum／validation hash、配對及 Xiaozhi 八項 live 符號、公開 CA／host 嵌入核對通過；產生的 host／CA／9443／9445 設定與服務配置一致，未嵌入本輪產生的私鑰或管理員憑證。分割表與原 8443 測試映像逐位元組相同，NVS 仍為 `0x9000`／`0x4000` 且不加密。新的機密目錄內摘要為 `validation-9445.json`；不因本機 bind 驗證成功而將 `device_tested` 標為通過。

下一步的待批准操作為 COM8 **ROM 模式唯讀辨識與 NVS 雙份備份**，包含操作員切入 ROM 及完成後恢復正常開機；不包含燒錄。操作員確認已在 ROM 模式後，先用 ESP-IDF Python 執行 esptool `--chip esp32s3 --port COM8 --before no-reset --after no-reset --no-stub read-mac` 核對 USB 身分，再執行既有 `firmware.capture_nvs_backup --port COM8 --table-offset 0x8000 --output-parent firmware/build/p204-bench-private`。工具先驗證分割表，再依表內範圍雙讀 NVS；結果與 9445 映像分割表作離線比對。若辨識、讀取或比對不符即停止。上述為尚未執行的具體計畫；須取得明確批准後才可開啟序列埠，實際燒錄位置與回復方案仍須另行審查。

2026-11-18，使用者批准上述 ROM 唯讀流程，並確認已依 [M5Stack 官方方式](https://docs.m5stack.com/en/arduino/m5cores3/program) 長按 RESET／RST 至綠燈亮後放開，進入下載模式。COM8 的 USB VID/PID／序號先行核對，再以 esptool 5.6.0 `no-reset`／`no-stub` 的 `read-mac` 確認 ESP32-S3（rev v0.2），ROM MAC 與 USB 序號一致。以既有捕捉工具的 `_read_flash` 與驗證函式依序讀取 `0x8000` 的 4 KiB 分割表 sector，再按有效 MD5 表內範圍獨立讀取兩份 NVS；本輪另行建立已核對絕對路徑的私人捕捉目錄，不自動刪除失敗資料。

兩份備份各 16,384 bytes，NVS 為 `0x9000`／`0x4000`，SHA-256 均為 `52a1637f14601ff7b912ea9512dfb38381ab14a2d76f0e3f47e4324cb054e59b`。捕捉分割表與 9445 映像的完整二進位表逐位元組相同，sector 尾部為全 FF；再以 `firmware.verify_nvs_backup --target-binary-partition-table` 離線複驗通過。原始備份、分割表與序列紀錄存於 `firmware/build/p204-bench-private/cores3-nvs-20261118-dkhnaway/`，Git 忽略且具受限 ACL；去除私有路徑及原始資料的證據在 `evidence/p204_cores3_nvs_capture_20261118.json`。這證明兩次讀取一致及來源／目標分割配置相容，不代表備份已實際回復成功，也不代表已有現行 app／整片 Flash 的回復映像。

讀取完成後，再次 `read-mac` 並使用已批准的 watchdog reset 恢復開機；此操作使用重設暫存器，未執行 Flash／eFuse 寫入。最初序列判定僅比對少數標籤而漏掉 `esp_image`／`SystemInfo`；額外的 ROM 再連線發生 Write timeout，未執行其預定的 hard-reset。後續核對原始紀錄含 `SystemInfo` 啟動訊息，操作員亦確認原 StackChan／Xiaozhi 畫面恢復且觸控可操作，才將恢復開機記為通過。未觀察到完整 SPI flash boot 訊息，不能把該欄誤標為通過；語音、網路重連、Agent 通知、現行啟動槽及備份回復仍未驗收。本輪沒有燒錄、清除 Flash、上傳 stub 或寫入 NVS／eFuse，P2-04 保留未完成。

## 4. 狀態仲裁矩陣

P2-04 的獨立控制器核心使用固定 RAM，最多保留四個待派送識別碼及其單調時鐘期限。這是實作上限；MVP 呼叫端應使用 `kCoreS3MvpRuntimeProfile`（經 `sanitizeRuntimeProfile`）。控制器從 Suspended 開始，只有當新連線送出通過穩定門檻的心跳後才可收取及取出通知。政策到期、心跳逾時、連線撤銷或時鐘倒退會阻止取件並清除佇列。心跳不延長政策期限。

裝置端 `DeviceStreamIngress` 接收已解碼的心跳和通知。它核對本機 Session ID、裝置、政策版本與 generation，使用綁定時的可信 UTC 樣本及之後的單調時鐘換算租約和通知期限。心跳時間戳在同一連線內須嚴格遞增，超齡、早於本次綁定或晚於推算 UTC 的封包會被拒絕。網路接線時須驗證時鐘同步與時間戳解析精度，並量測可接受的封包年齡和逾時門檻。

`DeviceStreamTlsClient` 已以 ESP-IDF TLS＋WebSocket transport 完成主機名檢查、固定 CA、HTTP 101 升級與分片／超限 Fail-Closed；Windows transport 替身測試通過，ESP32-S3 物件編譯通過。Coordinator 側已驗證 loopback「GET policy → MVP dispatcher → device-stream」軟體端到端（`test_loopback_policy_to_stream`）。裝置端已串起 `fetchAndProvisionDeviceStream`＋`startProvisionedDeviceStream`；Windows CTest 通過。`firmware/main/CMakeLists.txt` 以 `STACK_CHAN_NOTIFICATION_SOURCES` 明確釘住 notifications 翻譯單元（ESP-IDF script-mode 不可用 `CONFIGURE_DEPENDS`）；2026-11-17 `idf.py reconfigure` 成功且 managed `78/esp-ml307` hash 與 `dependencies.lock` 一致。全量 `idf.py build` 已通過；因尚無執行期呼叫端，`--gc-sections` 曾丟棄 notifications，故以 `link_anchor.cpp`（函式位址表）＋`-u stackchan_notifications_mvp_retain` 保留 MVP 進入點且不啟動 TLS／UI。最終 ELF 以 `nm -C` 確認 `sanitizeRuntimeProfile`／`parsePolicyLeaseJson`／`fetchAndProvisionDeviceStream`／`startProvisionedDeviceStream`／`completeDeviceLoopbackHandshake` 為 live 符號；`stack-chan.bin` 0x39ec50（app 區仍約 27% free）。裝置軟路徑握手 `completeDeviceLoopbackHandshake`（policy JSON→provision→bindVerified）與 pytest live TLS 裝置標頭契約已通過；實機燒錄與 R-006 失聯上界仍待完成。呼叫端須驗證 Coordinator 身分、裝置範圍、政策撤銷與完整 JSON 契約後才能綁定，並為重連或政策更新分配新的遞增本機 Session ID。控制器及 ingress 由單一執行上下文使用。

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

P2-09：`NotificationAudioGate`＋`kMvpAgentAudioCapability=A0` 凍結純 UI；授權／Audio 租約／playCue／playTts 在 A0 下 Fail-Closed，且不連結到 `Application::PlaySound`。升級 A1／A2 需另開 Gate 與人類授權，不得以本項宣稱 TTS 完成。

驗收使用本機 ESP32-S3 ELF 的符號表確認八個播放、取消與重設函式已連結，並驗證內建通知素材含 Ogg Opus 標頭（6,191 bytes）。全套 Python 回歸 150 項通過。CoreS3 音訊行為與停止時間仍待實機驗收。

## 6. Motion 安全

上游 `Motion::setModifyLock` 只是 bool，不是 Mutex；原廠 IMU Modifier 也會使用此旗標。通知 MotionAdapter 必須在提交前檢查 Arbiter、generation、可用角度與速度。`Motion::stop()` 將當前角度設成目標，**不代表已證明物理立即停止**。對 Yaw（可能有連續轉動模式）與 Pitch 分別測試。機構停止優先於回中心，避免突然碰撞；禁用任意外部指令直達 Servo。

### P0-05 主機端驗證

- 本機 `Motion::setModifyLock()` 直接寫入旗標。Idle Motion 與 Head Pet 會讀取，`Motion::move*()` 本身照常將指令轉給 Servo。IMU 晃動反應只在旗標未設時設定旗標並呼叫 `goHome(300)`，反應結束時直接清除旗標。這條路徑沒有所有者識別，控制權交接須由後續仲裁驗證。
- `Motion::stop()` 對兩軸各呼叫 `move(getCurrentAngle())`。`Servo::move()` 更新動畫目標。Yaw 的 `rotate()` 另走 PWM 模式，位置模式切換發生在後續位置寫入路徑。`stop()` 的回傳無法證明 PWM 已清除或機構已停止。Pitch 的堵轉保護可收窄位置限制並另行更新目標。
- `Hal::servo_init()` 的位置模式軟體預設值為 Yaw −128.0° 至 +128.0°、Pitch +3.0° 至 +87.0°。Windows MSVC／CMake／CTest 已驗證正規化映射的中心、兩端與超界裁切。這些預設值尚未經 CoreS3 實測確認可作為安全行程。

待驗證項目包括 Yaw 位置／PWM 模式的停止、Pitch 的實際停止與機構行程，以及晃動反應期間的控制權交接。

2026-11-16 使用者同意進行小幅實機測試。CoreS3 `COM8` 記錄 Xiaozhi 原廠介面先回報 Yaw −1°、Pitch 37°，再送出 Yaw +4°、Pitch 37°、速度 150 的位置指令。隨後又出現 Yaw +19°、Pitch 37°、速度 150 的指令，超出本次規劃的小幅操作，因此停止追加動作。序列紀錄僅證明位置指令進入韌體，未取得停止後角度、機構動作觀察或取消證據。語音工具可用於既有功能觀察，精確的停止與交接測試應使用確定的本機輸入。

## 7. Avatar／Mew

`StackChanAvatarDisplay::SetupUI` 建立 DefaultAvatar 與 Breath/Blink/HeadPet/IMU 等 Modifier。Mew Presenter 應可掛載完整身體圖層與通知狀態動畫，並保持原廠表情、睡眠、喚醒與觸控事件。若使用 `ShowNotification()`，需補全權限、時序、清除、ACK，不應直接把外部文字渲染到不受控視圖。SD 卡優先，素材驗證／解碼在低優先背景工作。欠缺 SD 時回內建角色，CoreS3 不留通知歷史。

## 8. 實機測試 Gate

必驗證：原廠 Xiaozhi 喚醒／對話／重進；多次同時 Agent 通知；Coordinator 突然斷線時清屏與音訊取消；Generation 舊回呼；LVGL Lock 占用時間；Servo 安全停止／搖晃 IMU；SD 缺失／損壞；PSRAM 峰值；看門狗；至少一次長時間穩定性執行，測試時長與合格線由 Phase 0 訂立。


### P2-04 OTA metadata 與現行 app 唯讀備份（2026-11-18）

上一輪 NVS 備份／正常畫面恢復已重驗並提交 `8e8b66d`（pytest 362/362、host CTest 31/31）。本輪依操作員確認的 ROM 模式重新核對 COM8 裝置身分及分割表；新增 `firmware/verify_ota_selection.py`，依本機 ESP-IDF 6.1 的 `bootloader_common_loader.c` 核對序號 CRC、有效狀態、最大序號與相同序號取第一筆規則。16 個測試涵蓋已知 CRC、雙份選擇、損壞／無效紀錄、全擦除 fallback、過渡狀態與錯誤輸入；完整 pytest 378/378 通過。解析器不模擬 anti-rollback、映像檢查或 bootloader fallback scan，輸出不等於執行期 running-partition API 確認。

兩份獨立 otadata 相同：第一筆 seq=1、state=VALID、CRC 正確，第二筆為擦除紀錄。metadata 選擇 ota_0，offset `0x20000`、size `0x4f0000`；ota_1 僅確認首個 header 為擦除狀態，未驗證整個分割區。no-stub 的完整 app 讀取及 1 MiB 分塊先後超時，保留不完整資料；取得使用者明確追加批准後，才改用 esptool 官方 RAM stub 的 `read-flash`，每次讀取一個完整指定範圍。stub 僅在 RAM，重啟後消失；未執行 Flash／eFuse 寫入命令。

完整 ota_0 的兩份獨立備份各 5,177,344 bytes，SHA-256 均為 `7a022d4863ff602923159324905a3ae5440d0ebbcc46d8e4726753f743fc999e`。esptool 驗證原 app checksum 與內附 SHA-256 均通過；原始映像長度 3,796,048 bytes、版本 1.6.2、ESP-IDF v6.1。另取兩份 NVS，摘要與上一輪一致。備份與原始映像只存放 Git 忽略的受限私人目錄，公開摘要見 `evidence/p204_cores3_app_capture_20261118.json`。備份完整性不代表已實際回復成功。

Assets 原始位元組與 9445 建置不同，因此另依 `assets.cc` 的 12-byte header／44-byte entry／ZZ magic 解析、核對 checksum 與範圍：兩邊均 42 個檔案、檔名與尺寸相同；40 個內容完全相同，`index.json` 只有換行與 emoji／extra_files 順序差異，正規化排序後物件相同。依 ESP-SR `model/pack_model.py` 格式比對 `srmodels.bin`，三個模型檔內容完全相同，只有封裝順序差異。這是保留原 Assets 的離線證據，新 app 的 UI／喚醒／音訊仍須實機回歸。

恢復開機 reset 後，操作員確認原畫面與觸控恢復，未將語音或網路視為通過。本輪沒有燒錄；候選 app 仍為 SHA-256 `9440c93901eded259792f6ffe7ca8bbc949bafaa5b0013cdd25a4bd98d8ca92b`，若後續另獲批准，以 app-only 寫入 `0x20000`，預計 sector 擦除範圍為 `[0x20000, 0x3c8000)`，不應使用完整 `idf.py flash`。bootloader、分割表、otadata、Assets、NVS 不在該寫入範圍；但新 app 執行期的原廠 NVS 初始化仍可能在 NO_FREE_PAGES／NEW_VERSION 時清除 NVS，不能保證運行後絕不改動 NVS。實際寫入與回復步驟仍須另行批准、校驗與測試；P2-04 保留未完成。


### P2-04 app-only 實機驗收與 I/O 時序修正（2026-11-18）

上一輪以 pytest 378/378、host CTest 31/31 及 app／NVS 雙備份、OTA metadata、候選映像 SHA 重驗後提交 `d16fd31`。依使用者本輪批准，先確認同一 CoreS3 的 MAC／USB 身分與安全摘要：flags=0、Secure Boot／Flash Encryption 關閉、SPI_BOOT_CRYPT_CNT=0、六個金鑰槽用途仍為 USER。候選 sdkconfig 關閉加密、anti-rollback、ROM download mode 禁用及 ROM 日誌燒寫設定；最終 ELF 無 eFuse 寫入函式，核對 IDF 啟動分支後才操作。未執行任何 eFuse 寫入命令。

先取得完整 16 MiB Flash 私人備份，再核對既有 app、NVS、otadata、分割表與 Assets 符合上一輪。只以 esptool `write-flash` 寫入 `9440c939…8ca92b` app，保留 Flash mode／frequency／size，offset `0x20000`、長度 3,830,176 bytes。esptool 寫入 hash 通過；開機前重新讀取完整 16 MiB，確認候選映像逐位元組相同、sector 尾部為 FF，且 `[0x20000, 0x3c8000)` 以外所有位元組完全未變，包括 bootloader、NVS、otadata、分割表及 Assets。安全摘要前後一致；不能將此摘要等同逐位元 eFuse 全量比對。原始 Flash／序列紀錄保留私人忽略目錄，公開證據見 `evidence/p204_cores3_app_only_20261118.json`。

reset 後序列日誌確認從 ota_0 載入新 ELF（前綴 `46d39d2e4`）。曾於 `Aw9523` 初始化 `stackchan.cc:229` 發生 I²C `ESP_ERR_INVALID_RESPONSE`，`I2cDevice::WriteReg` 觸發 abort；解碼 backtrace 顯示位於 HAL 初始化、通知任務啟動之前。自動重啟後進入 LVGL／Wi-Fi 並見 SNTP time synchronized。這不能排除回歸，開機穩定性仍未通過，不擅自改動原廠硬體初始化。

操作員從實機提供兩筆配對確認碼；第一筆由 loopback 管理 CLI 拒絕，DB 狀態 rejected 且無 completed_at。操作員隨後提供新碼，第二筆核准後 DB completed 並發出一個 device grant；實機診斷確認 policy／WebSocket upgraded。拒絕畫面文字尚未獨立確認；成功串流約 40 ms 即 disconnected，不能把持續串流或完整正向驗收記為通過。資源採樣為 task stack 最低剩 2,180 bytes、內部 heap 低水位 39,828 bytes、最大連續塊 31,744 bytes；只是單次握手樣本，不代表長時間或壓力驗收。

主機回歸測試以 socket read 耗時 2 ms 重現時序錯誤：client.poll 使用較新的 monotonic 時間後，loop.tick 卻收到呼叫端讀取前的舊時間，誤觸時鐘倒退保護。修正 `notification_product_loop_poll.cpp`，在讀取完成後重新取樣單調時間；保留呼叫端時間的下界與原本 client 的真實倒退檢查。新增測試修正前確實失敗，修正後通過，並確認真正 heartbeat 到期與時鐘倒退仍斷線。完整重建 host targets 後 CTest 31/31、pytest 378/378 通過。

修正版 ESP32-S3 app 六步建置及 checksum／digest 通過，長度 `0x3a71c0`、最小 app 分割區剩 26%；SHA-256 `14f81c8febb56878d81ca084d209102d6ec941718cf970c5d6e38eb7479d3af5`。sdkconfig 與分割表未變，ELF 無 eFuse 寫入函式；副本存於私人目錄 `clock-fix-app.bin`。此修正版尚未燒錄，已提出同一 app-only 範圍的具體批准請求。等待期間已關閉三個 listener 與 serial capture，核對埠已釋放。持續串流、重啟後 RAM 憑證失效與重新配對、原廠語音／網路共存、AW9523 異常與備份實際回復仍待驗收；P2-04 保留未完成。
