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

`DevicePolicyLeaseService` 實作 `GET /v1/devices/{deviceId}/policy` 契約門面：僅同裝置 `device:policy` 憑證可讀；回傳 OpenAPI `Policy` 快照並衍生 `expires_utc_ms` 供裝置綁定。未綁定、撤銷、過期、版號不符、錯 scope 或跨裝置讀取皆 Fail-Closed（403）。`serve_device_policy` 提供 `127.0.0.1` loopback TLS HTTP／1.1 端點，校驗客戶端信任鏈後回傳 JSON；未授權／錯 scope／撤銷政策回傳 Error schema。尚未部署對外非 loopback listener。

CoreS3 的 `parsePolicyLeaseJson` 接受上述 Policy JSON（固定欄位、可選 `revoked:false`），將 `valid_until` 轉成 UTC 毫秒並在本機時鐘已同步且租約未到期時允許 `bindPolicyLease`。過期、`revoked:true`、未知 `privacy_mode`、尾隨資料或超限皆拒絕。產出的 `version`／`expires_utc_ms` 供 `DeviceStreamTlsClient::Config` 使用。

`PolicyLeaseHttpClient` 以 ESP-IDF TLS transport 對 Coordinator 發出 `GET /v1/devices/{deviceId}/policy`：明確 CA、拒絕轉址／非 200、要求 `Content-Length` 與本文一致，再交給 `parsePolicyLeaseJson`；`applyPolicyLeaseToStreamFields` 填入 stream 的 `policy_version`／`policy_expires_utc_ms`。Windows transport 替身測試通過；與 loopback server 的端到端實機路徑仍待驗證。

`provisionDeviceStream` 將已驗證租約與（經 `sanitizeRuntimeProfile` 的）MVP runtime profile 組成 `DeviceStreamTlsClient::Config`（含 frame／network 上限與政策欄位），Fail-Closed 於過期租約或非法 profile；本身不建立連線。

`fetchAndProvisionDeviceStream` 先以同一組主機／CA／token 透過 `PolicyLeaseHttpClient` 取得租約，再呼叫 `provisionDeviceStream`；HTTP 失敗或租約無效則不產生 Config，且不開啟 device-stream WebSocket。

`startProvisionedDeviceStream` 以已佈建 Config 呼叫 `DeviceStreamTlsClient::start`（呼叫端須用同一 profile 建構客戶端）；空／不一致的 provision Fail-Closed。Windows 替身測試涵蓋「取租約→佈建→WebSocket 101 升級」軟路徑。

Coordinator loopback 整合：`serve_device_policy` 取得 Policy 後，以 `create_mvp_notification_dispatcher`（MVP capacity／heartbeat）搭配 `serve_device_stream`，用租約 `version` 升級 WebSocket 並收到 heartbeat／intent；錯版號拒絕。裝置軟路徑 `completeDeviceLoopbackHandshake` 消費同一 Policy 快照並 `bindVerified`；pytest `test_device_loopback_handshake` 以裝置 StreamProvision 標頭對 live loopback TLS 完成握手。實機燒錄路徑與 R-006 仍待驗證。

CoreS3 的 policy GET 與 WebSocket 共用設定的 TLS 主機及連接埠。Coordinator 可將 `DevicePolicyLeaseService` 傳給 `serve_device_stream(..., policy_leases=...)`，於同一個 `127.0.0.1` TLS listener 同時提供兩條路徑。policy 仍只接受 HTTP/1.1 GET，並驗證裝置範圍及 `device:policy` 權限。WebSocket 按既有規則驗證 `device:stream` 與政策版號。未提供 policy service 時仍可分開開啟兩個 loopback listener。CoreS3 尚需經受控網路路徑驗收。

本機可用 `stackchan coordinator serve-device` 啟動同埠驗收服務。需指定既有安全資料庫（`--security-db`）、TLS PEM 憑證及私鑰（`--cert`、`--key`）、連接埠（`--port`，0 由系統分配）與 `--generation`。以環境變數 `STACKCHAN_SECURITY_PEPPER` 傳入既有資料庫使用的 pepper（UTF-8），服務以唯讀模式開啟資料庫，並在標準輸出回報實際本機埠。此啟動入口使用 MVP 設定及初始空的通知佇列，可驗證 policy、升級與心跳。 預設綁定 `127.0.0.1`。經批准的實機驗收可指定 `--listen` 為主機的 RFC 1918 IPv4，且須以 `--device-ip` 指定唯一允許的 CoreS3 私有 IPv4。兩條 HTTP 路徑在進入授權前都核對實際 TCP peer，TLS 握手仍可先發生，裝置仍須驗證伺服器憑證並提供各路徑所需的 Bearer 授權。Coordinator 憑證須符合裝置使用的主機名或 IP。

P2-04 MVP 容量／逾時：裝置 `kCoreS3MvpRuntimeProfile` 與 Coordinator `CORE_S3_MVP_RUNTIME_LIMITS` 對齊（capacity 4、heartbeat 4s、stability 5s、frame age 5s、frame 1024 bytes、network 10s；Coordinator heartbeat_interval 1s、pong_timeout 2s）。超出硬上限的設定 Fail-Closed。R-006 上界 4185 ms 已與 firmware／Coordinator 對齊；CoreS3 實測樣本 revoke_ms=4000（見 evidence/r006_device_revoke_measure.md）。

P2-04 產品主迴圈：`NotificationProductLoop` 以單一 `tick` 組裝 FailClosedGuard＋佇列 takeNext＋Presenter；`notificationProductLoopPollClient` 僅在 `DeviceStreamTlsClient::started()` 時 poll（未佈建不開 TLS）。`CONFIG_STACKCHAN_AGENT_NOTIFICATIONS`（default n）於 `_stackchan_update_task` 在 LVGL lock 外呼叫 `tickNotificationProductRuntime`；預設韌體不啟用。實機 Coordinator 連線與 Avatar UI 仍待後續 Gate。

P2-04 憑證／arm：`armProvisionedDeviceStream`（已 started 則拒絕）與 `fetchAndArmDeviceStream`（GET policy→provision→arm）提供 Fail-Closed 軟路徑；`armNotificationProductRuntime` 僅接受已驗證 `StreamProvision`，init 不自動 fetch。host 替身測試覆蓋空 provision／雙重 arm／401 upgrade。產品路徑須沿用預設 NVS 既有格式，裝置端通知憑證採短效 RAM 佈建。RAM 佈建與實機 Coordinator 串流仍待驗收。

CoreS3 的 `DeviceStreamTlsClient` 使用 ESP-IDF TLS transport 包裝 WebSocket，固定連線到設定主機的 `/v1/device-stream`。它使用明確提供的 Coordinator CA 並保留主機名稱檢查，僅接受 HTTP 101，遇到 HTTP 轉址會關閉連線。呼叫端須在單一工作任務呼叫 `start`、`poll`、`takeNext`、`stop`，並供應已同步的時鐘、已驗證的政策快照及封包上限。單一 WebSocket 文字框可分多次 socket read 收取，超過上限或遇到 WebSocket 層分片會撤銷 session。斷線與心跳逾時同樣停權。Windows 測試使用 transport 替身，裝置憑證握手與到 Coordinator 的端到端網路路徑仍待實機驗證。

`serve_device_pairing` 在 `127.0.0.1` 提供獨立的 CoreS3 配對 HTTPS listener。建立配對成功時，回應標頭 `X-StackChan-Pairing-Claim` 傳回一次性領取碼，發起端須只存於 RAM 並避免記錄。管理員透過既有 `admin:pairing` 權限確認使用者代碼。完成端點要求發起端帶回領取碼，成功後消耗領取碼並傳回既有 `PairingCompleteResponse`。Coordinator 只在 listener 記憶體保留領取碼的雜湊及期限，關閉 listener 後，未完成的發起端須重新配對。啟動 listener 時，操作員可透過 device_policy 指定政策 ID 與版號。已核准的配對領取憑證時，新身分、指定政策綁定、授權 grant 與配對完成狀態在同一筆 SQLite 交易寫入。設定的政策不存在、撤銷或過期時，整筆回復並拒發憑證。省略 device_policy 時維持既有人工綁定流程。重新配對的新身分取得本次指定政策，各裝置的憑證只能讀取自己的政策。CoreS3 對真實 Coordinator 的 HTTPS 呼叫仍待實機驗收。

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

本機配對服務可用下列 CLI 啟動。`STACKCHAN_SECURITY_PEPPER` 必須已設定為既有安全資料庫使用的 pepper；資料庫須已初始化，並具備尚未撤銷、未到期且具有 `admin:pairing` 的管理員憑證。CLI 不建立管理員、不自動核准配對，也不輸出 token 或領取碼。

```powershell
stackchan coordinator serve-pairing --security-db security.sqlite --cert coordinator-cert.pem --key coordinator-key.pem --port 9443 --policy-id desk --policy-version v1
```

`serve-pairing` 預設綁定 `127.0.0.1`；未啟用下述 LAN 雙入口時，建立、確認及領取皆在同一個 loopback listener；`--port 0` 可使用系統分配的埠，標準輸出會回報實際埠。與唯讀的 `serve-device` 分開，配對服務以 SQLite `mode=rw` 開啟既有資料庫，允許配對狀態、grant 與政策綁定寫入，但不建立檔案或初始化／遷移 schema。政策 ID 與版本皆須明確提供，領取時仍由既有交易驗證政策有效性；未知、撤銷或到期政策拒發並回復交易。啟動成功不代表指定政策已通過領取驗證。

2026-11-18 驗收：`test_pairing_cli.py` 的 17 項測試通過，其中實際子程序／loopback TLS 涵蓋待核准、錯誤管理員、拒絕、成功後政策綁定、重複領取拒絕、程序重啟後舊領取碼失效與新配對成功，以及不可用政策的交易回復。另驗證缺 pepper、必要參數缺漏、非法埠、空白政策、LAN 選項拒絕、缺少／空白資料庫與啟動錯誤遮蔽。全套 pytest 302/302；host CTest 31/31。未變更韌體、未開 LAN listener；CoreS3 不能直接連至本機 loopback，受來源限制的 LAN 配對及實機驗收仍待完成。

經批准的 LAN 驗收可在 `serve-pairing` 明確指定 `--listen` 為主機 RFC 1918 IPv4、`--device-ip` 為唯一允許的 CoreS3 私有 IPv4，並以 `--admin-port` 指定另一個管理員 TLS 埠（可用 0 自動分配）。三項須搭配；拒絕萬用、公網、主機名稱、IPv6、相同主機／裝置 IP，以及缺少或非法管理埠。loopback 模式不接受 `--device-ip` 或 `--admin-port`。CLI 仍須使用既有 pepper、資料庫及明確政策 ID／版本。

```powershell
stackchan coordinator serve-pairing --security-db security.sqlite --cert coordinator-cert.pem --key coordinator-key.pem --port 9443 --policy-id desk --policy-version v1 --listen 192.168.1.10 --device-ip 192.168.1.20 --admin-port 9444
```

LAN 入口只接受指定 TCP peer 的建立與領取請求；即使帶有效管理員 token，確認路徑也回 403。管理入口固定綁定 `127.0.0.1`，只接受確認路徑，仍要求有效 `admin:pairing` 及正確確認碼，不能建立配對或領取 token。兩個入口共用同一份 RAM 領取碼雜湊與期限；拒絕／一次領取會更新共享狀態，重啟服務後舊領取碼失效。不信任 `X-Forwarded-For`；來源檢查在 TLS 握手後、HTTP 解析及授權前執行。TLS 憑證須同時適用於裝置連線使用的 LAN 主機名或 IP 與管理端使用的 `127.0.0.1`，且兩端都驗證 CA。標準輸出分別回報裝置與管理埠，不含 token、確認碼或領取碼。

兩個 listener 共用生命週期，均先完成綁定才開始服務；任一綁定／啟動失敗或服務取消時會關閉已建立的 listener。2026-11-18 新增 20 項測試：LAN 綁定位址與 TCP peer 使用替身，實際 TLS socket 僅綁定 loopback，驗證跨入口成功、來源與路徑拒絕、偽造轉送標頭、人工拒絕、重啟、CLI 參數轉交及失敗／取消清理。配對 CLI 專項共 37/37；完整 pytest 322/322，host CTest 31/31。本輪未開真實 LAN listener、改動韌體、寫入裝置 NVS 或 eFuse。真實網卡綁定、CoreS3 HTTPS、實機 RAM 憑證與 Xiaozhi 共存仍未驗收。

## 7. TTL、資料保留、背壓

- TTL 僅控制**是否仍值得主動呈現**，資料保留則控制 Bridge／Coordinator 的歷史清理。
- 待播放隊列在 Coordinator，CoreS3 RAM 僅保留有界的短期工作；記憶體上限由 Phase 0 實機量測決定。
- 重要且仍有效的等待／失敗事件優先；公平配額避免低優先事件永久飢餓；若已過 TTL 可以轉為歷史不主動播報。
- 清理資料時不得破壞 Outbox／sync cursor；尚未被對端 ACK 的紀錄應有明確持續重試與告警策略；不可重新匯入已按政策清理之事件。
- 禁止生成語義不明的「完成五項任務成功」，可以數量化已確認的事件並保留 `event_ids`。

## 8. API/DB 未完成 Gate

欄位格式、索引、資料表物理結構、錯誤碼、HTTP 身份機制、重放保護、WebSocket heartbeat 上界、TTL 預設值及保留期限尚未最終鎖定。開發前須通過 JSON Schema／OpenAPI 契約測試並明確版本化。
