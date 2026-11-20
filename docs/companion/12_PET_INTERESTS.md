# 12｜寵物興趣系統（v2.3.3）

> 狀態：**已確認需求、尚未實作**。本文件為 Raspberry Pi Pet Brain 的 MVP 設計，不表示原廠已有這些動畫或數據。

## 1. 使用者體驗與核心原則
StackChan 有自己的偏好和生活習慣。閱讀興趣較高時更常挑書，但也能工作、吃點心、探索與創作；心情不好或精力低時仍可能休息。**興趣只增加傾向，不直接強迫活動**。

五類興趣（建議固定 ID）：

| ID | 中文名稱 | 可映射的基礎動畫 | 影響 |
|---|---|---|---|
| `reading` | 閱讀 | `read`、思考、翻頁 | 探索知識、分享簡短心得 |
| `coding` | 研究與工作 | `work`、打字 | 模擬寫程式與研究 |
| `food` | 美食 | `eat`、開心 | 吃點心與食物話題 |
| `exploration` | 探索 | `walk`、`look_around` | 螢幕走動、觀察 |
| `creative` | 藝術與創作 | `create`（可先用簡化動畫） | 畫畫／想像創作 |

睡眠、休息、安靜與專注不是興趣；由精力與活動規則決定。

## 2. 資料及成長規則
- 每項興趣初始 `50`、範圍整數 `0–100`、附 `updated_at`。使用者可透過日常互動逐步影響興趣。
- **建議**：完成某類活動 +1；明確的正向互動 +2～3；單日同一興趣上升量設定上限，例如 +5；不因一句對話突然跳到 100。
- 長期沒出現的興趣可每週緩慢往 50 回歸（例如最多 1 分）；不永久失去興趣，也不令每週批次更新產生負面驚喜。
- 由 Pi 本地程式更新興趣數值，LLM **不得**直接提交 `reading=100` 等數值修改。
- 保存最後 20 次活動（數量可調），避免最近做過的活動反覆被選中；保留寵物生理需求優先權。

## 3. 下一個活動如何選擇
建議高階排程：

1. 確認目前是否在 `Companion + IDLE`，是否正在聽／說／通知、是否超時、是否安靜時段。
2. 準備候選活動、可用動畫、五項興趣、心情精力與最近歷史；精力偏低時提高睡眠優先級。
3. 達到決策間隔且 AI 額度允許時，請雲端 LLM 在**候選清單**中選擇活動與短情緒；AI 不可編造未實作的硬體能力。
4. 由 Pi 驗證；若不合法、逾時、超額，改用本地加權選擇（興趣偏好 + 新奇度 + 精力修正）。
5. StackChan 接收一個高階活動指令，在本機演出 5–20 分鐘左右的完整片段，期間的眨眼等小動作不呼叫 LLM。

## 4. 可測試的離線後備策略
假設 `weight = 1 + interest/20 + novelty_bonus + energy_modifier`，其中 `novelty_bonus` 對最近未做的活動較高。權重經過夾取，睡眠/休息由 energy 規則獨立評分；正規化後以偽隨機挑選。**公式是可調建議**，先用 seed 固定的測試確保行為多樣性，不把它當物理模型。

## 5. AI 高階輸出契約
```json
{
  "action": "read",
  "emotion": "curious",
  "duration_s": 480,
  "optional_short_line": "我再看一會兒書。",
  "reason_code": "interest_reading"
}
```

驗證：`action` 在白名單；`duration_s` 有上下限（建議 30–1200 秒）；`emotion` 限既有表情；短語有長度上限；`reason_code` 只供日誌／分析，不能執行任何操作。

## 6. SQLite 持久化
- `pet_interests(interest_id TEXT PRIMARY KEY, score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100), updated_at TEXT NOT NULL)`。
- `pet_activity_history(id INTEGER PRIMARY KEY, action TEXT, interest_id TEXT, started_at TEXT, ended_at TEXT, interrupted INTEGER)`。
- 首次啟動補齊缺失興趣；升級資料庫要有 schema version/migration；不覆蓋舊的寵物狀態。

## 7. 驗收標準
- 五項興趣初始化 50，手動/事件變化不越界、單日限制生效。
- 高興趣能提高活動出現機率，但沒有哪一個興趣佔滿所有活動；活動冷卻和精力狀態有效。
- SQLite 重啟持久，模型無法連線時靠本地規則仍可自行活動。
- 允許使用者重設興趣，不能讓模型直接刪除或修改資料表。

相關：`05_PI_SERVICES_AND_PET.md`、`13_PROACTIVE_INTERACTION.md`、`15_DATA_CONFIG.md`。
