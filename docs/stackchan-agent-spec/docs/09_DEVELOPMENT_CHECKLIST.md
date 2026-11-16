# 09｜唯一開發任務 Checklist（尚未開始實作）

> **此檔是本專案唯一正式任務追蹤清單。** 其他文件含驗收矩陣／風險表，但不建立獨立 task lists；每個任務的 PR／CI／證據應回填本清單。以下未勾選代表尚未實作／驗收，不能靠文件生成判定完成。**目前僅規劃，未授權動程式碼／建立分支／燒錄。**
>
> 勾選條件：任務完成、測試證據真實、風險 Gate 經授權，並填入 `Evidence: ...`；禁止空勾。

## Phase 0 — 前置技術調查／實作授權前

- [ ] **P0-01** 核對 `jason22432150/StackChan` 的 HEAD、Branch、上游差異與授權；`Evidence: 未提供`；Gate G0。
- [ ] **P0-02** 檢查 `firmware/repos.json`、Xiaozhi deps、patch 及實際 ESP-IDF 版本；`Evidence: 未提供`。
- [ ] **P0-03** 追蹤 Xiaozhi `Application`、音訊工作階段與安全提示音／TTS 入口，明確提出 A0/A1/A2 能力結論；`Evidence: 未提供`。
- [ ] **P0-04** 追蹤 `_stackchan_update_task`、LVGL lock 生命周期、Task 優先級與 PSRAM，保留基準量測；`Evidence: 未提供`。
- [ ] **P0-05** 查明 `Motion::setModifyLock`、IMU Modifier、Servo `stop()`、Yaw/Pitch 實機限制；`Evidence: 未提供`。
- [ ] **P0-06** 確認 CoreS3 SD 挂載、圖片載入格式與失敗路徑；`Evidence: 未提供`。
- [ ] **P0-07** 查驗 Codex 官方 Hooks／Cursor 事件及版本能力、ChatGPT/Grok 瀏覽器／UI 來源權限分級；`Evidence: 未提供`。
- [ ] **P0-08** 完成 Phase 0 風險與替代方案審查，必要的人類核准；`Evidence: 未提供`。

## Phase 1 — 契約／安全／基礎設施

- [x] **P1-01** 凍結 AgentEvent／NotificationIntent／PresentationReceipt JSON Schema 與契約 version；測試非法事件與跨版本行為；Gate G1。`Evidence: schema_version=0.1 FROZEN（CONTRACT_VERSION.md）；src/stackchan/contracts；uv run pytest tests/contracts -v → 57 passed（2026-11-16）。OpenAPI／授權 API 仍屬 P1-02，完整 G1 未關閉。`
- [x] **P1-02** 完成 OpenAPI、Error Schema、配對流程、Device Stream Envelope；驗證未授權 API 不可讀寫。`Evidence: openapi.yaml 補 NotificationIntent／Error／Pairing／device-stream 與 x-required-scopes；error／pairing／device-stream-envelope schema；ApiGate 未授權／錯 scope／撤銷拒絕；uv run pytest tests/contracts -v → 77 passed（含 P1-01 回歸，2026-11-16）。尚未部署真實 HTTP server。`
- [x] **P1-03** 完成 Bridge SQLite 交易、Observation ID、Outbox、重試與 epoch；斷電重試測試。`Evidence: src/stackchan/bridge/store.py（observations／event_log／outbox／sync_state／epoch）；tests/bridge/test_sqlite_outbox.py 含原子寫入、冪等、缺口 ACK、斷電前後重試；uv run pytest tests/bridge tests/contracts -v → 88 passed（2026-11-16）。尚未實作真實網路上傳。`
- [x] **P1-04** 完成 Coordinator SQLite 索引、追加式事件、任務投影、已讀與 Receipt DB Migration／索引測試。`Evidence: src/stackchan/coordinator/store.py（schema_migrations v1、events／event_evidence／task_projections／read_states／presentation_receipts／sync_cursors＋索引）；response.completed 不標 succeeded；已讀樂觀鎖；receipt 冪等；uv run pytest tests/coordinator tests/bridge tests/contracts -q → 96 passed（2026-11-16）。`
- [x] **P1-05** 完成分層身份／安全配對／政策版號／撤銷；審查對外網路暴露與密鑰保護。`Evidence: src/stackchan/security/（SecurityStore 僅存 token_hash、PairingService、PolicyService Fail-Closed、DEFAULT_BIND_HOST=127.0.0.1、redact_secrets）；ApiGate+撤銷；uv run pytest tests/security tests/coordinator tests/bridge tests/contracts -q → 103 passed（2026-11-16）。尚未部署對外 HTTP listener。`
- [ ] **P1-06** 完成版本化設定、短期保留政策與清理水位；不得在清理後重導入過期事件。
- [ ] **P1-07** 確認單一開發清單／CI PR 契約測試規範；高風險合併需授權。

## Phase 2 — 核心 MVP 的 Bridge／Coordinator／CoreS3

- [ ] **P2-01** Windows Bridge CLI 基本執行、受授權 Codex／Cursor Adapter、證據等級、事件格式轉換。
- [ ] **P2-02** 追加式批次同步、ACK 缺口、重送冪等、時鐘偏差測試；Gate G2。
- [ ] **P2-03** Coordinator 基本優先排程、TTL、Fail-Closed、穩定重連與異常診斷。
- [ ] **P2-04** CoreS3 建立安全 NotificationController、有限 RAM 佇列及 policy lease。
- [ ] **P2-05** CoreS3 ResourceArbiter、Generation Token、取消確認、舊 callback 失效。
- [ ] **P2-06** 透過既有 LVGL lock 整合基礎 UI／Mew 中性與成功通知；絕不繞過 Xiaozhi。
- [ ] **P2-07** 裝置 Accepted／Started／Completed／Interrupted 收據與多次 ACK 冪等。
- [ ] **P2-08** 斷線即中斷已呈現內容，Xiaozhi 不受影響，CoreS3 實機成功；Gate G3。
- [ ] **P2-09** 按 Phase 0 音訊能力 A0/A1 進行安全短提示音；若無驗證維持純 UI，不宣稱完成 TTS。

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
