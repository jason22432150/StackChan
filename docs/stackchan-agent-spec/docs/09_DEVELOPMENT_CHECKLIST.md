# 09｜唯一開發任務 Checklist（尚未開始實作）

> **此檔是本專案唯一正式任務追蹤清單。** 其他文件含驗收矩陣／風險表，但不建立獨立 task lists；每個任務的 PR／CI／證據應回填本清單。以下未勾選代表尚未實作／驗收，不能靠文件生成判定完成。**目前僅規劃，未授權動程式碼／建立分支／燒錄。**
>
> 勾選條件：任務完成、測試證據真實、風險 Gate 經授權，並填入 `Evidence: ...`；禁止空勾。

## Phase 0 — 前置技術調查／實作授權前

- [x] **P0-01** 核對 `jason22432150/StackChan` 的 HEAD、Branch、上游差異與授權。 `Evidence: 04_FIRMWARE_XIAOZHI.md §1（2026-11-16）；git ls-remote／merge-base／rev-list 驗證 upstream main 28b9f0c、fork my-stackchan-01 4a39d51、本機 feature/agent-notifications f7f11f4；本機分別領先 16／13 筆，均無落後；韌體依賴／patch 差異檢查通過。授權限本輪本機工作，G0 整體仍未關閉。`
- [x] **P0-02** 檢查 `firmware/repos.json`、Xiaozhi deps、patch 及實際 ESP-IDF 版本。 `Evidence: 35773eb（Windows，2026-11-16）；repos.json 六筆本機 HEAD 符合指定 ref；Xiaozhi v2.5.2 = 49b4380b3faa0ceadd28a3e78aaf0f311c46c57e，既有 patch 在暫存 Git index 可正向套用，結果與依賴工作樹追蹤檔完全一致，反向檢查亦通過。idf.py --version → v6.1.0，符合 dependencies.lock；idf_tools.py check-python-dependencies 通過；Ninja ESP32-S3 增量建置 39 步通過，最小 app partition 剩 27%；esptool image-info 驗證 checksum／hash，映像 ESP-IDF v6.1、ELF SHA256 d48d0c9eae777e1ac37e580d54b406e8367ed8bdedd4d44b4ccad1d19cf2dc20。未燒錄或進行 CoreS3 實機驗收。`
- [x] **P0-03** 追蹤 Xiaozhi `Application`、音訊工作階段與安全提示音／TTS 入口，明確提出 A0/A1/A2 能力結論。 `Evidence: 04_FIRMWARE_XIAOZHI.md §5；00af989／Xiaozhi v2.5.2 + 既有 patch（2026-11-16）；原始碼追蹤對話、短提示音與 notify 路徑，ESP32-S3 ELF 八個連結符號與內建 Ogg Opus 素材驗證通過；全套 pytest 150 passed。維持 A0；A1/A2 與實機音訊搶占未驗證。`
- [x] **P0-04** 追蹤 `_stackchan_update_task`、LVGL lock 生命周期、Task 優先級與 PSRAM，保留基準量測。 `Evidence: 04_FIRMWARE_XIAOZHI.md §3；f7f11f4／CoreS3（2026-11-16）。雙設定物件編譯、診斷版全量建置及 ota_0 寫入校驗通過；映像 SHA256 077493621748ad45170a80cff2b982c1e3e205c3706fed7227ec7622d6957545。COM8 捕捉 41 個視窗，確認待機／聆聽／回覆與回到待機；最大更新間隔 184,054 µs、最大持鎖 117,429 µs、內部 heap 低水位 5,424 bytes、PSRAM 低水位 7,555,464 bytes。P2-04 容量與 lease 上界仍待決定。`
- [ ] **P0-05** 查明 `Motion::setModifyLock`、IMU Modifier、Servo `stop()`、Yaw/Pitch 實機限制。 `Evidence: 04_FIRMWARE_XIAOZHI.md §6（2026-11-16）；已追蹤 ModifyLock、IMU 與 stop／PWM 模式路徑，Windows MSVC／CTest motion_math_test 1/1、Python 回歸 150 passed。CoreS3 COM8 已確認原廠語音介面收到 Yaw 位置指令，因出現超出本輪小幅測試的第二筆指令而停止追加操作。實機停止、機構行程及 IMU 交接尚未驗證。`
- [ ] **P0-06** 確認 CoreS3 SD 挂載、圖片載入格式與失敗路徑；`Evidence: 未提供`。
- [x] **P0-07** 查驗 Codex 官方 Hooks／Cursor 事件及版本能力、ChatGPT/Grok 瀏覽器／UI 來源權限分級。 `Evidence: 11_EVIDENCE_SOURCES.md §5（2026-11-16）；官方 Hook／瀏覽器文件與本機 Codex CLI 0.156.1、Cursor IDE 3.30.14 版本核對；Adapter／Bridge／契約測試 111 passed，完整 pytest 150 passed。本項為能力與授權稽核，真實 Hook 投遞及 P4-02 UI Adapter 尚未驗證。`
- [ ] **P0-08** 完成 Phase 0 風險與替代方案審查，必要的人類核准；`Evidence: 未提供`。

## Phase 1 — 契約／安全／基礎設施

- [x] **P1-01** 凍結 AgentEvent／NotificationIntent／PresentationReceipt JSON Schema 與契約 version；測試非法事件與跨版本行為；Gate G1。`Evidence: schema_version=0.1 FROZEN（CONTRACT_VERSION.md）；src/stackchan/contracts；uv run pytest tests/contracts -v → 57 passed（2026-11-16）。OpenAPI／授權 API 仍屬 P1-02，完整 G1 未關閉。`
- [x] **P1-02** 完成 OpenAPI、Error Schema、配對流程、Device Stream Envelope；驗證未授權 API 不可讀寫。`Evidence: openapi.yaml 補 NotificationIntent／Error／Pairing／device-stream 與 x-required-scopes；error／pairing／device-stream-envelope schema；ApiGate 未授權／錯 scope／撤銷拒絕；uv run pytest tests/contracts -v → 77 passed（含 P1-01 回歸，2026-11-16）。尚未部署真實 HTTP server。`
- [x] **P1-03** 完成 Bridge SQLite 交易、Observation ID、Outbox、重試與 epoch；斷電重試測試。`Evidence: src/stackchan/bridge/store.py（observations／event_log／outbox／sync_state／epoch）；tests/bridge/test_sqlite_outbox.py 含原子寫入、冪等、缺口 ACK、斷電前後重試；uv run pytest tests/bridge tests/contracts -v → 88 passed（2026-11-16）。尚未實作真實網路上傳。`
- [x] **P1-04** 完成 Coordinator SQLite 索引、追加式事件、任務投影、已讀與 Receipt DB Migration／索引測試。`Evidence: src/stackchan/coordinator/store.py（schema_migrations v1、events／event_evidence／task_projections／read_states／presentation_receipts／sync_cursors＋索引）；response.completed 不標 succeeded；已讀樂觀鎖；receipt 冪等；uv run pytest tests/coordinator tests/bridge tests/contracts -q → 96 passed（2026-11-16）。`
- [x] **P1-05** 完成分層身份／安全配對／政策版號／撤銷；審查對外網路暴露與密鑰保護。`Evidence: src/stackchan/security/（SecurityStore 僅存 token_hash、PairingService、PolicyService Fail-Closed、DEFAULT_BIND_HOST=127.0.0.1、redact_secrets）；ApiGate+撤銷；uv run pytest tests/security tests/coordinator tests/bridge tests/contracts -q → 103 passed（2026-11-16）。尚未部署對外 HTTP listener。`
- [x] **P1-06** 完成版本化設定、短期保留政策與清理水位；不得在清理後重導入過期事件。`Evidence: Coordinator migration v2（app_settings／purged_events／cleanup_watermarks）；RetentionService 候選 7/14/30、預設 14 未鎖死；清理僅限 contiguous 內過期事件；tombstone 拒絕重導入；uv run pytest tests/retention tests/coordinator tests/security tests/bridge tests/contracts -q → 106 passed（2026-11-16）。`
- [x] **P1-07** 確認單一開發清單／CI PR 契約測試規範；高風險合併需授權。`Evidence: .github/workflows/agent-contracts.yml；docs/12_CI_PR_NORMS.md；tests/meta/test_ci_pr_norms.py；uv run pytest … -q → 110 passed（2026-11-16）。未設定 GitHub branch protection（需人工）。`

## Phase 2 — 核心 MVP 的 Bridge／Coordinator／CoreS3

- [x] **P2-01** Windows Bridge CLI 基本執行、受授權 Codex／Cursor Adapter、證據等級、事件格式轉換。`Evidence: src/stackchan/adapters（Codex／Cursor）；bridge/service.py＋cli.py；agent-turn-complete／stop→response.completed（不推導 succeeded）；白名單 source_payload；uv run pytest tests/adapters tests/bridge … -q → 133 passed（含回歸，2026-11-16）。尚未做真實網路上傳（P2-02）／未改韌體。`
- [x] **P2-02** 追加式批次同步、ACK 缺口、重送冪等、時鐘偏差測試；Gate G2。`Evidence: src/stackchan/sync（BridgeSyncClient／CoordinatorSyncApi／InMemoryTransport／clock）；ACK 丟失重送冪等、序號缺口游標、SUSPENDED Fail-Closed、跨 Bridge 時鐘不 LWW；uv run pytest tests/sync … -q → 142 passed（含回歸，2026-11-16）。尚未部署真實 HTTPS。`
- [x] **P2-03** Coordinator 基本優先排程、TTL、Fail-Closed、穩定重連與異常診斷。 `Evidence: src/stackchan/coordinator/dispatch.py；有界佇列、優先配額、派送前 TTL／憑證／政策查驗、心跳與穩定門檻、固定原因計數；.venv\Scripts\python.exe -m pytest tests/coordinator/test_dispatch.py tests/security -q → 15 passed；全套 pytest → 150 passed（2026-11-16）。證據限 Coordinator 程序內；待派送佇列存於記憶體，尚未接上 WebSocket 或 CoreS3。`
- [ ] **P2-04** CoreS3 建立安全 NotificationController、有限 RAM 佇列及 policy lease。 `Evidence: 04／03（2026-11-17）；loopback＋R-006；ProductLoop 掛點；`armProvisionedDeviceStream`／`fetchAndArmDeviceStream`／`armNotificationProductRuntime`（Fail-Closed、不自動 fetch）。host CTest 21/21；pytest 211；`idf.py build` bin 0x39ed40／SHA256 D8D568EA…。CoreS3 產品 arm 入口比對六項 MVP profile 限制，任一不符即在連線前拒絕。macOS host CTest 21/21，包含六項個別不符、未初始化拒絕及相符時成功升級。全套 pytest 211 passed。ESP-IDF 6.1 ESP32-S3 建置通過，app partition 剩 27%（通知功能關閉的本機設定）。NVS 唯讀載入器以替身驗證，涵蓋未啟用加密、必要欄位缺漏／無效、長度超限及讀取失敗。macOS host CTest 23/23，全套 pytest 211 passed。ESP-IDF 6.1 本機預設映像建置通過，app partition 剩 27%。以真實 ESP-IDF 標頭另行交叉編譯啟用加密的讀取器物件，編譯通過。真實加密 NVS、產品啟動接線、實機 Coordinator stream 與 Avatar 仍待驗收。`
- [x] **P2-05** CoreS3 ResourceArbiter、Generation Token、取消確認、舊 callback 失效。 `Evidence: resource_arbiter.h／.cpp（2026-11-17）；beginPresentation／tryAcquire／mayCommit／cancelCurrent／revokeAll／onXiaozhiActivity；T-SEC-03 舊 Generation 延遲 callback 不可 commit；Xiaozhi Busy 立即撤 Audio／Motion 並讓出 UI，Idle 後同 Generation 可重取；取消確認同步回傳且不阻塞子系統 ACK。host CTest 12/12（含 resource_arbiter_test）；uv run pytest -q → 186 passed；idf.py build 通過，ELF nm 可見 resourceArbiterCommitGate，link_anchor 保留；stack-chan.bin 0x39dd70、partition 剩 27%、SHA256 2E6305A5…D95707FA。未燒錄；未接 Presenter／LVGL／Audio／Motion adapter（屬 P2-06）；音訊仍維持 A0。`
- [x] **P2-06** 透過既有 LVGL lock 整合基礎 UI／Mew 中性與成功通知；絕不繞過 Xiaozhi。 `Evidence: notification_presenter.h／.cpp、LvglLockedUiPort、makeHalLvglLockHooks（2026-11-17）；Neutral／Success 經 ResourceArbiter mayCommit 後才 show；interrupt／Xiaozhi Busy 先撤權再 clear；LVGL lock hooks 對齊 Hal::lvglLock／Unlock（同 LvglLockGuard）。host CTest 14/14（含 notification_presenter_test）；uv run pytest -q → 188 passed；idf.py build 通過，ELF nm 可見 makeHalLvglLockHooks／notificationPresenterMayPresent；stack-chan.bin 0x39e240、partition 剩 27%、SHA256 62E9A744…34425BEF。未燒錄；ShowNotification 仍為空、未掛入 StackChanAvatarDisplay／Mew 全身（實機畫面屬 P2-08／P3）；音訊仍 A0。`
- [x] **P2-07** 裝置 Accepted／Started／Completed／Interrupted 收據與多次 ACK 冪等。 `Evidence: presentation_receipt.h／.cpp（2026-11-17）；狀態機 accepted→started→(completed｜interrupted｜cancelled｜failed)；每狀態獨立 receipt_id；重複 receipt_id／Coordinator 多次 ACK 回 Duplicate；終態後可開新 delivery；JSON 拒跳脫字元。host CTest 13/13（含 presentation_receipt_test）；uv run pytest -q → 188 passed（含裝置編碼金樣契約）；idf.py build 通過，ELF nm 可見 encodePresentationReceiptJson，link_anchor 保留；stack-chan.bin 0x39e1a0、partition 剩 27%、SHA256 F841AF8D…D954E7B6。未燒錄；未接 Presenter／HTTP POST receipts（P2-06／後續 transport）；未改 Xiaozhi。`
- [ ] **P2-08** 斷線即中斷已呈現內容，Xiaozhi 不受影響，CoreS3 實機成功；Gate G3。 `Evidence: FailClosedGuard＋R-006 probe 實測 revoke_ms=4000≤4185（2026-11-17）。診斷 probe 非常駐主迴圈；Gate G3（Presenter 掛入 Avatar／實機畫面）仍未完成——不得勾完成。`
- [x] **P2-09** 按 Phase 0 音訊能力 A0/A1 進行安全短提示音；若無驗證維持純 UI，不宣稱完成 TTS。 `Evidence: notification_audio_policy.h／.cpp（2026-11-17）；kMvpAgentAudioCapability=A0；NotificationAudioGate 拒絕 audio／tts 政策、拒絕 Audio 租約、playCue／playTts 不呼叫 sink；不 include PlaySound／AudioCodec。host CTest 16/16（含 notification_audio_policy_test）；uv run pytest -q → 190 passed（含 test_p209_audio_a0_policy）；idf.py build 通過，ELF nm 可見 mvpAgentAudioIsA0；stack-chan.bin 0x39e8d0、partition 剩 27%、SHA256 EA670AE7…71169544。A1／A2 未驗證、不宣稱 TTS；純 UI。未燒錄。`

## Phase 3 — Mew、SD、音訊／語音追問

- [ ] **P3-01** PC 端整備 Mew 全身素材與聲明式動畫時間軸，資源預算清單。
- [ ] **P3-02** SD 角色載入、內建原廠角色備援、格式／checksum／路徑驗證。
- [ ] **P3-03** Avatar／Modifier 與 Blink／Breath／IMU 關係、資源搶占及狀態恢復實機測試。
- [ ] **P3-04** Motion 安全取消、角度限制、碰撞測試及硬體授權預覽。
- [ ] **P3-05** 依 Phase 0 經確認的原廠 Audio Service 實作通知 TTS，確保與 Xiaozhi 互斥／共存；不可直接音訊 Codec 注入。
- [ ] **P3-06** 依原廠能力實現唯讀、隱私分級的語音追問，確認不增加預設 OpenAI API 付費需求。
- [ ] **P3-07** 通知模板與 Web 時間軸編輯器、Windows LVGL 模擬器，實機 Gate G4。

## Phase 4 — 多平台、Dashboard、進階隱私

- [ ] **P4-01** macOS／Linux Bridge 安裝、CLI＋Tray／Local Web、跨平台重送與升級。
- [ ] **P4-02** Browser／Desktop UI Adapter 能力矩陣與誤報節流測試；Grok／ChatGPT 按實際授權整合。
- [ ] **P4-03** 多 CoreS3 路由、獨立派送、全域已讀版本同步與衝突更正。
- [ ] **P4-04** Agent 唯讀 Dashboard、檢索、資料最小化和權限檢查。
- [ ] **P4-05** 情境隱私規則＋裝置獨立解鎖、政策版本／撤銷／Fail-Closed 實機驗證。
- [ ] **P4-06** Bridge/Coordinator Docker／NAS、LAN/VPN／可選中繼、安全設定備份。
- [ ] **P4-07** 手動韌體與素材回復操作說明、一鍵基本遮蔽診斷匯出。

## Phase 5 — 完整驗收與發行

- [ ] **P5-01** 依 `07_TEST_ACCEPTANCE.md` 建立全部自動化測試紀錄、故障注入報告。
- [ ] **P5-02** CoreS3 原廠 Xiaozhi 音訊、Servo、SD、LVGL、長時間穩定性人工驗收；Gate G5。
- [ ] **P5-03** 逐項對照 #1～#96 的 traceability、依賴、版本變更與殘餘風險。
- [ ] **P5-04** 技術規格從 v0.1 草案修正到可批准 v1.0，人工檢核並授權 Merge、燒錄及 OTA（如有）。

## 開發紀律

- Contract-first；一項工作有清楚輸入／輸出／測試／風險／前置依賴，未通過不得勾。
- 可以在獨立分支／worktree 並行工作，但高風險操作需明確人類授權。
- CI 不取代 CoreS3 硬體驗收；模擬器不是實機通過證據。
- 不自行改變已定義 Fail-Closed、單使用者、無 Agent 遠端控制、無 CoreS3 通知歷史等底線。
