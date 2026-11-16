# 03｜事件、API、SQLite 與可靠同步契約

## 1. 三種契約

- **AgentEvent**：由 Bridge 建立的標準觀測，含 `event_id`（內部）、`observation_id`（本次觀測）、`source_event_id`（來源可選）、`source_task_id`（可選、不可偽造）、`bridge_id`、`adapter_id`、`event_type`、`evidence_level`、`observed_at`、`privacy_class`、`bridge_sequence`。原始資料僅保存白名單授權欄位。
- **NotificationIntent**：Coordinator 根據事件和隱私政策產生，含 `notification_id`、`delivery_id`、`event_ids`、`device_id`、`priority`、`expires_at`、`policy_version`、`generation`、允許呈現項目。
- **PresentationReceipt**：CoreS3 回報 `receipt_id`、`delivery_id`、`attempt_id`、`device_id`、`generation`、`status`、`reason`；是裝置流程證明，不是使用者看見證明或已讀。

Schema 參考 `../contracts/*.schema.json`。Schema 的 enum 是本案規格語義，不聲稱任何 Agent 官方原生支援。

## 2. 事件語義與可信分級

| event_type | 解釋 | `task.succeeded` 是否可推導 |
|---|---|---|
| `task.started` | 任務開始 | 否 |
| `task.running` | 任務執行中 | 否 |
| `task.awaiting_user` | 等待操作 | 否 |
| `task.succeeded` | 有明確成功證據 | 已明確標記成功 |
| `task.failed` | 有明確失敗證據 | 否 |
| `task.cancelled` | 任務取消 | 否 |
| `response.completed` | 一次回應輸出完畢 | **否** |
| `observation.uncertain` | 推測或不確定 | **否** |

證據等級 `verified`、`observed`、`inferred`、`unknown` 與事件語義**獨立**。verified response.completed 仍不得播成 task.succeeded。不同來源若對同一工作矛盾，保留追加式證據並標記衝突，不能按抵達時間武斷選真相。

## 3. HTTP API 與權限

| Path | 方向 | 目的 | 權限 |
|---|---|---|---|
| `POST /v1/events/batch` | Bridge→Coordinator | 多事件冪等匯入 | `bridge:write` |
| `GET /v1/sync/status?bridge_id=...` | Bridge→Coordinator | 連續 ACK 與缺口查詢 | `bridge:sync` |
| `GET /v1/events` | Dashboard→Coordinator | 遮蔽篩選歷史 | `dashboard:read` |
| `POST /v1/events/{eventId}/read` | 使用者／裝置→Coordinator | 明確已讀 | `read:write` |
| `GET /v1/devices` | Dashboard→Coordinator | 裝置狀態 | `dashboard:read` |
| `GET /v1/devices/{deviceId}/policy` | CoreS3→Coordinator | 帶版號的政策 | `device:policy` |
| `POST /v1/deliveries/{deliveryId}/receipts` | CoreS3→Coordinator | 呈現收據 | `device:receipt` |
| `GET /v1/health` | 管理端→Coordinator | 不含秘密的健康狀態 | `admin:health` |
| `WS /v1/device-stream` | Coordinator↔CoreS3 | 通知、取消、存活及政策更新 | `device:stream` |

`openapi.yaml` 為**提案樣板**，與 WebSocket 封包細節分開；不表示原始碼存在端點。正式版還須補入配對協定、錯誤碼與連線狀態事件。

P2-04 的 Coordinator 編碼器將 `heartbeat` 與 `notification.intent` 序列化為 UTF-8 JSON。通知外層的 device、delivery、policy version 與 generation 取自同一份意圖。時間以 UTC 毫秒輸出，截斷更細的精度，並拒絕在送出時已到期的通知。device、policy version 和 delivery ID 須能放入裝置的 128-byte 欄位，generation 使用 uint64。凍結 schema 維持原版本。

呼叫端須先驗證裝置連線與政策，再選取意圖並編碼。相同毫秒內重複編碼心跳會得到相同時間戳，因此網路傳送端仍須依裝置入口規則安排嚴格遞增的心跳。

裝置端解碼器接受 Coordinator 編碼器使用的緊湊 UTF-8 JSON 與固定 UTC 毫秒格式。呼叫端在解碼前提供已驗證連線的本機 Session ID 和封包位元組上限。裝置會拒絕重複欄位、尾隨資料、無效編碼與範圍不一致的意圖，再交給既有入口驗證心跳和租約。解碼器會暫時配置 JSON 記憶體，正式位元組上限及解碼峰值須在 CoreS3 量測。

Coordinator 的 `serve_device_stream` 提供 `127.0.0.1` 的 `/v1/device-stream`，呼叫端提供 TLS 憑證與伺服器設定。升級時驗證 Bearer 憑證、`X-StackChan-Device-Id`、`X-StackChan-Policy-Version` 與裝置的 `device:stream` scope。每次收到 WebSocket Pong 後重驗授權，才送出應用層心跳及符合伺服器 generation 的意圖。未回 Pong、授權失效或連線中斷時清理派送 session。現階段意圖在取件後離開暫存佇列，若 Socket 在寫入時中斷可能遺失該筆派送。CoreS3 實際連線、收據及線上重送仍待接線。

`DevicePolicyLeaseService` 實作 `GET /v1/devices/{deviceId}/policy` 契約門面：僅同裝置 `device:policy` 憑證可讀；回傳 OpenAPI `Policy` 快照並衍生 `expires_utc_ms` 供裝置綁定。未綁定、撤銷、過期、版號不符、錯 scope 或跨裝置讀取皆 Fail-Closed（403）。尚未部署真實 HTTP listener。

CoreS3 的 `parsePolicyLeaseJson` 接受上述 Policy JSON（固定欄位、可選 `revoked:false`），將 `valid_until` 轉成 UTC 毫秒並在本機時鐘已同步且租約未到期時允許 `bindPolicyLease`。過期、`revoked:true`、未知 `privacy_mode`、尾隨資料或超限皆拒絕。產出的 `version`／`expires_utc_ms` 供 `DeviceStreamTlsClient::Config` 使用；尚未接上真實 HTTP GET。

P2-04 MVP 容量／逾時：裝置 `kCoreS3MvpRuntimeProfile` 與 Coordinator `CORE_S3_MVP_RUNTIME_LIMITS` 對齊（capacity 4、heartbeat 4s、stability 5s、frame age 5s、frame 1024 bytes、network 10s；Coordinator heartbeat_interval 1s、pong_timeout 2s）。超出硬上限的設定 Fail-Closed。實機失聯撤銷時間仍待 R-006。

CoreS3 的 `DeviceStreamTlsClient` 使用 ESP-IDF TLS transport 包裝 WebSocket，固定連線到設定主機的 `/v1/device-stream`。它使用明確提供的 Coordinator CA 並保留主機名稱檢查，僅接受 HTTP 101，遇到 HTTP 轉址會關閉連線。呼叫端須在單一工作任務呼叫 `start`、`poll`、`takeNext`、`stop`，並供應已同步的時鐘、已驗證的政策快照及封包上限。單一 WebSocket 文字框可分多次 socket read 收取，超過上限或遇到 WebSocket 層分片會撤銷 session。斷線與心跳逾時同樣停權。Windows 測試使用 transport 替身，裝置憑證握手與到 Coordinator 的端到端網路路徑仍待實機驗證。

## 4. 建議 SQLite 邏輯實體

**Bridge**：`observations`、`event_log`、`outbox`、`sync_state`、`adapter_state`、`bridge_settings`。

**Coordinator**：`events`、`event_evidence`、`task_projections`、`notifications`、`notification_events`、`deliveries`、`delivery_attempts`、`presentation_receipts`、`read_states`、`sync_cursors`、`devices`、`privacy_policies`、`authorization_grants`、`diagnostic_errors`。

**索引與約束**：`events.event_id UNIQUE`；`observations.observation_id UNIQUE`；`(bridge_id, epoch, bridge_sequence) UNIQUE`；`receipts.receipt_id UNIQUE`；外鍵關聯 `delivery_id`／`attempt_id`／`device_id`；全域已讀使用版本號。Bridge 本地 SQLite 交易中原子寫入 event + outbox。Coordinator 寫入成功且交易提交後才能發出持久 ACK。

## 5. 批次同步

1. Adapter 提交來源事件；Bridge 判定合法欄位與證據，建立穩定內部識別與本地序列。
2. Bridge 同一個本地交易中寫 `event_log`、`outbox`，`outbox` 起始 `pending`。
3. Bridge 在可信連線上上傳批次（`bridge_id`、`epoch`、每筆 `bridge_sequence`、`event_id`、最小化事件）。
4. Coordinator 驗簽／來源身份、schema、大小／版本，冪等持久化，回覆每筆成功與失敗，以及連續 ACK 游標。
5. Bridge 只把真正已持久確認的事件標為同步，未確認者限速重送；ACK 丟失可再次上傳同一 Event ID。
6. 如果 101 與 103 成功而 102 失敗，連續游標僅推至 101；103 為暫存的非連續 ACK，待 102 補齊後才推進。
7. Bridge 安裝重建或本機 sequence 歸零需使用新的 epoch；不能把時鐘當作唯一主鍵。

**一致性模式**：At-Least-Once 傳輸＋冪等儲存／呈現，而不是虛構 Exactly-Once 網路保證。跨 Bridge 的先後因果只有在來源可靠時才認定，否則隔離為未確認關聯。

## 6. 通知與呈現狀態

`notification`: created→queued→dispatched→（裝置 `accepted`→`started`→`completed`／`interrupted`／`failed`），另有 cancelled／expired／suppressed／aggregated。單一意圖可能包含多個 `event_ids`；`aggregated` 表示呈現策略，不刪原始事件。`ReadState` 是獨立、顯式的使用者操作，不可由 presented／completed 推導。

每次派送有 `attempt_id` 與有效 generation；過期 generation 的 ACK 可以記錄診斷但不得復活已失效通知。若通知 TTS 開始但隨後被 Xiaozhi 搶占，receipt 應保留 `interrupted`，不能回報 `completed`。

## 7. TTL、資料保留、背壓

- TTL 僅控制**是否仍值得主動呈現**，資料保留則控制 Bridge／Coordinator 的歷史清理。
- 待播放隊列在 Coordinator，CoreS3 RAM 僅保留有界的短期工作；記憶體上限由 Phase 0 實機量測決定。
- 重要且仍有效的等待／失敗事件優先；公平配額避免低優先事件永久飢餓；若已過 TTL 可以轉為歷史不主動播報。
- 清理資料時不得破壞 Outbox／sync cursor；尚未被對端 ACK 的紀錄應有明確持續重試與告警策略；不可重新匯入已按政策清理之事件。
- 禁止生成語義不明的「完成五項任務成功」，可以數量化已確認的事件並保留 `event_ids`。

## 8. API/DB 未完成 Gate

欄位格式、索引、資料表物理結構、錯誤碼、HTTP 身份機制、重放保護、WebSocket heartbeat 上界、TTL 預設值及保留期限尚未最終鎖定。開發前須通過 JSON Schema／OpenAPI 契約測試並明確版本化。
