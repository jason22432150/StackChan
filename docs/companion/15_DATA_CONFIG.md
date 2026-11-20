# 15｜資料結構、配置與 API 合約示例（v2.3.3）

> 這裡是**待實作規格**，示例欄位可依程式語言微調，但需維持資料持久化、版本遷移與安全邊界。

## 1. SQLite 建議最小 Schema
```sql
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS pet_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  mood INTEGER NOT NULL DEFAULT 50 CHECK (mood BETWEEN 0 AND 100),
  energy INTEGER NOT NULL DEFAULT 70 CHECK (energy BETWEEN 0 AND 100),
  affinity INTEGER NOT NULL DEFAULT 50 CHECK (affinity BETWEEN 0 AND 100),
  activity INTEGER NOT NULL DEFAULT 50 CHECK (activity BETWEEN 0 AND 100),
  current_action TEXT NOT NULL DEFAULT 'idle',
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pet_interests (
  interest_id TEXT PRIMARY KEY,
  score INTEGER NOT NULL DEFAULT 50 CHECK (score BETWEEN 0 AND 100),
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pet_activity_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT NOT NULL,
  interest_id TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  interrupted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS user_preferences (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  summary TEXT NOT NULL,
  importance INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proactive_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  decision TEXT NOT NULL,
  reason TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_events (
  event_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  title TEXT,
  summary TEXT,
  confidence TEXT NOT NULL DEFAULT 'unverified',
  created_at TEXT NOT NULL,
  read_at TEXT
);
```

- 第一次啟動建立 pet_state id=1 與五種興趣各 50；schema_version 從正式 migration 開始，不因加欄位重置舊資料。
- P0 不儲存大量原始錄音或完整逐字稿；偏好／重要事件用短摘要，提供刪除/重設方式。
- 所有時間戳儲存 UTC ISO 8601，顯示/日界線使用設定時區（預設 Asia/Taipei）。
- 日誌與資料庫不得存 API Key。定期備份、設定資料保留期限與大小上限。

## 2. `coordinator/config.example.yaml`（不含密鑰）
```yaml
app:
  timezone: Asia/Taipei
  host: 0.0.0.0          # 只在可信任 LAN 使用，路由器不得 Port Forward
  port: 8765
  log_level: INFO

device:
  boot_mode: companion  # 實際開機模式以 StackChan 設定同步為準
  heartbeat_seconds: 5
  session_timeout_seconds: 15
  max_text_chars: 160

llm:
  active_provider: provider_a
  providers: [provider_a, provider_b]
  timeout_seconds: 25
  max_pet_plans_per_day: 48
  daily_spend_usd_soft_limit: 1.0  # 僅本地估計，並非供應商硬性帳單上限

voice:
  activation: [touch, keyword]
  keyword_name: "小智"  # 實際能否辨識須在 Phase 2 驗證
  interrupt: touch
  raw_audio_retention: false

pet:
  personality: natural
  mood_initial: 50
  energy_initial: 70
  interests_initial: 50
  action_min_seconds: 30
  action_max_seconds: 1200
  recent_activity_window: 20

proactivity:
  focus_mode: false
  quiet_hours: { start: "23:00", end: "08:00" }
  voice_max_per_day: 3
  voice_min_interval_minutes: 90
  bubble_min_interval_minutes: 20
  bubble_max_interval_minutes: 60

notifications:
  companion_only: true
  max_resume_summary: 5
  retention_days: 7

storage:
  db_path: ./data/companion.db
  raw_audio_save: false
```

實際 secrets 請放在 Pi 本機的 `.env` 或受限環境檔（如 `PROVIDER_A_API_KEY=...`），**絕不可放進 Git、StackChan 韌體或 WebSocket 控制訊息**。`daily_spend_usd_soft_limit` 是本機軟限制，供應商帳單管理仍需由使用者在官方平台設定。

## 3. HTTP / WebSocket 最小介面
- `GET /health`：Pi 服務狀態，避免包含 token 或敏感對話。
- `GET /api/status`：當前 Companion 模式、模型名、寵物狀態摘要（需本機或授權）。
- `POST /api/events`：電腦 Bridge 事件，獨立最小 token，需去重；P1 接入真 Agent，MVP 可測試假事件。
- `WS /ws/device`：StackChan 建立已配對會話、狀態機、控制/音訊影格，詳細見 `03_PROTOCOL.md`。
- 設定更動先經 Pi 的受限本機管理方式；不必為個人版製作大型 RBAC。

## 4. 配置與資料遷移測試
- `.env` 未設定金鑰時能用 mock provider 執行測試，且 Pi 啟動時清楚顯示「雲端模型尚未配置」。
- `config.yaml` 遺漏新欄位，仍有保守預設值，不會重設已存在的興趣／寵物關係。
- 連續升級／退回版本須保存備份，不可在資料庫 schema 不相容時靜默清空。
