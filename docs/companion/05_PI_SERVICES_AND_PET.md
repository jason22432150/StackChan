# 05｜Pi AI、寵物自主、長期記憶與通知

## 部署架構
單一 Python 服務，FastAPI + asyncio + SQLite + systemd，使用 Raspberry Pi OS 64-bit；不需 Docker 或企業級服務。

```text
coordinator/
  app/main.py                  # 程式入口與生命週期
  app/config.py                # YAML + env，含 active_llm_provider
  app/device_ws.py             # StackChan WebSocket
  app/audio_pipeline.py        # STT / TTS、音訊緩衝與取消
  app/wake_word.py             # Pi 偵測器（若實機選此路）
  app/providers/base.py        # 小型 LLM Adapter 介面
  app/providers/provider_a.py  # 雲端模型 A
  app/providers/provider_b.py  # 雲端模型 B
  app/assistant.py             # 使用者語音對話與回應
  app/pet.py                   # 角色心情、親密度及活動狀態
  app/pet_planner.py           # LLM 自主行為選擇與白名單驗證
  app/memory.py                # 偏好／重要事件／關係記憶
  app/notifications.py         # Agent 事件與 Companion-only 顯示
  app/storage.py               # SQLite
  app/events_api.py            # 電腦 Bridge HTTP
  config.example.yaml
  data/                        # 不提交 Git
  tests/
```

## 多模型切換（MVP）
- 支援**至少兩個真正的雲端 LLM provider adapter**，介面簡單：`generate_reply(context, user_text)`、`choose_pet_action(context)`，回傳標準化資料。供應商可依實際選擇，例如 OpenAI／Gemini；**不假設使用者已持有任何 API 金鑰**。
- `active_llm_provider` 設定可修改；更換 LLM 只動 Pi，不需要重新燒錄 StackChan；STT/TTS 初期可以各固定一種服務，之後逐步抽換。
- 失敗：顯示錯誤並回 Idle；可選手動換備用提供者，避免隱性跳轉造成未知費用。測試需有假 provider 可無金鑰執行。
- Provider key 只放 Pi 的受限 `.env`/環境變數；不要將對話與金鑰寫入除錯日誌。
- 設定 API 額度/每日預算上限（個人版簡單計數即可），防止自主活動頻繁消耗 token。

## AI 自主行為（MVP）
- 角色狀態：`mood`、`energy`、`affinity`、`activity`，數值 0–100；並有 `current_action`、`quiet_hours`、`last_interaction_at`。
- Pi 在**上一段活動結束、重要事件發生或使用者互動後**，才向 LLM 發起下一步行為建議，另設最小請求間隔（初始建議 60–180 秒，之後量測調整）；不是每幀詢問。
- LLM 只能選：`idle, sleep, read, work, eat, walk, look_around, celebrate` 等預先允許行為；可附 `emotion`、`optional_short_line`、`duration_s`。限制 `duration_s`、語音播報頻率及夜間動作。
- **在線時 AI 決定多數活動**；雲端斷線、超額、timeout 時改用本地低頻規則與現有 `idle_motion` 備援。
- 單一動作 owner；任何輸出都先經 Pi 驗證，再由 StackChan 再次限位。避免突發多個轉頭要求／音訊重疊。

### 模型建議的示例（僅邏輯，不直接傳硬體）
```json
{"action":"read","emotion":"curious","duration_s":45,"optional_short_line":"我來看一下書！"}
```

## 記憶與儲存（MVP）
SQLite 最小表格：
- `pet_state(id,mood,energy,affinity,activity,current_action,updated_at)`：寵物狀態。
- `user_preferences(key,value,updated_at)`：暱稱、安靜時間、個性偏好等使用者明確指定的設定。
- `memories(id,kind,summary,importance,created_at)`：重要事件與關係互動摘要；提供可查看／刪除方式。
- `agent_events(event_id,source,status,title,summary,confidence,created_at,read_at)`：Agent 事件，P1 正式接入。
- 可配置保留天數與最多條數；預設不存原始錄音、完整對話全文，避免過度占用空間與隱私問題。
- AI 讀取相關偏好與近期重要記憶，不讓每次 prompt 無限制成長。重開機後可恢復狀態。

## 通知策略：只有 Companion 模式（P1）
- Windows/macOS/Linux Bridge 使用可靠事件接口優先；原生 hook > 日誌 > UI 推測。UI 推測不能當成確定成功。
- Pi **可在任何模式記錄事件**，但裝置處於 `factory_ai/launcher/other` 時**不發出任何通知顯示／聲音／動作指令**。
- Companion 內，使用者對話時通知排隊；多筆合併摘要；重新進入時只顯示未讀且不過期的通知摘要，避免一次大量播報。
- 使用 `event_id` 去重；成功／失敗與來源可信度分開儲存；重要事件必要時納入寵物記憶。

## 開機與更新
- Pi 在 systemd 中自啟；新的 LLM/寵物規則只改 Python，再重啟該服務，StackChan 自動重連。
- 不做複雜 OTA 平台；Pi 更新先備份 SQLite/config 並保留上一個 Git commit，若服務無法啟動可回退。
- 第一張 128GB microSD 給 Pi；第二張保留。不要將韌體中內嵌的資源誤認為可自動從 StackChan microSD 載入。

## v2.3.3：Pet Interest System + Natural Proactivity
在先前 `app/pet.py`、`app/pet_planner.py` 基礎上，建議新增小型 `app/pet_interests.py` 與 `app/proactivity.py`，**仍為單一 Python 服務**。

**興趣維度：** reading、coding、food、exploration、creative；每項 0–100，初始中性分數，緩慢調整。睡覺不是興趣，而是由 energy 決定的生理狀態。保留活動最近歷史避免同一選項一直勝出。

**AI 選擇：** 先由 Pi 根據心情、精力、時段、偏好、最近活動整理候選，再請 LLM 從可用候選中決定高階行為。LLM 只提交 `{action, emotion, duration_s, optional_short_line}`；程式檢查後才執行。雲端失敗時採用本機加權選擇；避免為眨眼等低階事件消耗 token。

**自然主動互動：** 預設以非語音小動作為主；文字泡泡較少；主動語音極少（初始建議每日≤3、間隔≥90 分鐘）。`quiet_hours`（初始 23:00–08:00）、`focus_mode`、`user_dialogue_active`、`speaking`、`device_mode` 任一限制生效就不得主動播音。主動說完若無回覆，不追問。

**自主與安全取捨**：使用者已選 AI 決定大部分活動，此處指**高階活動選擇**，不是授權 AI 繞過物理馬達限位、佔用音訊或修改設定。模型費用、每日自主決策總次數與 API timeout 需在 Pi 可設定。

**SQLite** 新增 `pet_interests`、`pet_activity_history`、`proactive_log` 三表，保持簡單索引與有限事件保留。完整欄位與設定範例見 `15_DATA_CONFIG.md`，細節見 `12_PET_INTERESTS.md` 與 `13_PROACTIVE_INTERACTION.md`。
