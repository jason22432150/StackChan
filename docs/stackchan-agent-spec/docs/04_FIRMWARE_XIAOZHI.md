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

`loadNotificationCredentials` 在啟用 `CONFIG_NVS_ENCRYPTION` 時以唯讀方式開啟已初始化的預設 NVS 命名空間 `agent_notify`。`port` 為非零 u16，`host`、`device_id`、`token`、`ca_pem` 為字串，上限依序為 253、128、512、3,999 bytes。讀取出錯或任一欄位無效即回傳無憑證。PEM 僅檢查文字邊界，信任鏈及主機名由後續 TLS 握手驗證。產品端由呼叫端明確呼叫 `fetchAndArmNotificationProductRuntime`，傳入 Coordinator 的 generation。入口先檢查 runtime 已初始化、尚未連線，且本次開機已收到既有 SNTP 同步回呼。只有 RTC 或正值的系統時鐘時，入口不讀憑證也不連線。同步確認在同一次開機保留。通過檢查後，入口取樣系統 UTC 毫秒、讀憑證、透過 TLS 取得 policy，再以同一組憑證及已驗證的租約升級 WebSocket。通知 tick 使用同一個 UTC 毫秒來源。初始化與閒置 tick 不會讀取憑證或發起連線。呼叫端須與 init、arm、tick 在同一執行上下文序列化，且在 LVGL lock 外執行，因 TLS 可能阻塞。憑證寫入、產品觸發來源與實機握手仍待驗收。

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
