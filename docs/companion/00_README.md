# StackChan Companion v2.3.3 — 開發文件總覽

> 日期：2026-11-20｜狀態：需求定稿／尚未實作｜用途：供 Codex 或工程師直接依規格分階段開發。

## 專案目標
保留現有 `jason22432150/StackChan` 分支 `my-stackchan-01` 的原廠 Xiaozhi、Launcher、Avatar、Dance、Setup、OTA；**新增 Companion App 入口**。Raspberry Pi 4B 作為 AI 大腦，經雲端模型提供 STT/LLM/TTS、長期偏好記憶、寵物自主行為與 Agent 事件整合；StackChan 收音、播放、顯示文字／表情／動畫、觸控與轉頭。

## 8 項已確認使用者決策（v2.3 變更基準）
1. **多模型切換**：Pi 可從設定切換至少兩個雲端 LLM 提供者／模型；STT/TTS 可先用各一種服務，介面保留替換空間。
2. **觸控＋喚醒詞都能開始對話**：兩種入口同等重要，納入 MVP；喚醒詞為可設定值，偵測位置由實測決定。
3. **先觸控打斷 AI 說話**：語音打斷與全雙工留到後續版本。
4. **Companion 為主要模式**：正常開機可預設進 Companion，原廠主選單和 Xiaozhi 仍能切回；故障安全退回 Launcher。
5. **Agent 通知只在 Companion 模式顯示／播報**：退出 Companion 後絕不可覆蓋原廠 App；Pi 可儲存事件，重新進入時顯示合理摘要。
6. **AI 自主決定大部分寵物活動**：Pi 使用雲端 LLM 選擇活動、表情、短句等；只允許安全白名單動作，離線時本機規則維持運作。
7. **長期記憶**：保存使用者偏好、寵物關係與重要事件；預設不長期儲存原始錄音或所有對話全文。
8. **直接安裝 Python 服務**：Raspberry Pi OS 上單一 Python Coordinator + systemd + SQLite；不強制 Docker。

## 不可違反原則
- 個人使用、功能完整、流暢優先；拒絕企業級微服務、Kubernetes、Redis、多租戶 IAM 等非必要複雜度。
- 原廠功能**不刪除不替代**；Companion 是新增 App，雙方同時間只由一個模式掌控音訊、UI、馬達。
- **禁止新增任何 eFuse 寫入**，包括自動燒入 Secure Boot／Flash Encryption eFuse。
- Pi 使用第一張 **128GB microSD**；第二張 **128GB 暫留**，StackChan 暫不依賴 SD 卡。
- 雲端 API key 留在 Pi，絕不放入 StackChan 韌體或 Git；雲端 API 費用不等於 ChatGPT Plus 費用。

## 版本與來源基線
- Repository：https://github.com/jason22432150/StackChan
- 主要分支：`my-stackchan-01`
- 已確認 commit：`4a39d5114c5d8ea555444396434918db6a0f5656`；**開發前重查 HEAD**。
- 建議開發分支：`feature/stackchan-companion`（尚未建立）。
- 技術基礎：ESP-IDF v6.1、Mooncake、LVGL、ESP32-S3、Raspberry Pi 4B、Python asyncio/FastAPI。

## 文件清單
| 檔案 | 目的 |
|---|---|
| `00_README.md` | 總覽與不可變需求 |
| `01_ARCHITECTURE.md` | 全系統架構、啟動、資源控制、離線策略 |
| `02_MVP_SCOPE.md` | MVP P0 必要功能與可驗收標準 |
| `03_PROTOCOL.md` | Pi↔StackChan 控制／音訊協定 |
| `04_FIRMWARE_INTEGRATION.md` | 對原廠程式碼的精確整合位置 |
| `05_PI_SERVICES_AND_PET.md` | 多模型、AI 自主、記憶、通知、儲存 |
| `06_DEVELOPMENT_PLAN.md` | 可依序實作與測試的階段 |
| `07_TEST_SAFETY.md` | 效能、品質、安全與回退 |
| `08_AI_IMPLEMENTATION_PROMPT.md` | 可貼給 Codex 的工作指令 |
| `09_SOURCES_AND_ASSUMPTIONS.md` | GitHub 證據與待查事項 |
| `10_DECISIONS_v2.3.md` | 8 項決策與舊版差異 |
| `18_PHASE1_FIELD_ISSUES.md` | Phase 1 實機問題、根因與解法紀錄 |

## 狀態說明
「已確認」表示確認源碼存在基礎，不代表完成實機驗證；「設計」表示開發目標。**目前尚未修改 GitHub，未燒錄或測試硬體。**

## v2.3.1 新增：StackChan microSD 設定頁
- 在 StackChan **原廠 SETUP → Device → Storage / microSD** 新增獨立儲存資訊頁（不依賴 Pi 連線）。
- 顯示 microSD 掛載狀態、總容量、剩餘容量、已用容量、使用率；支援重新檢查與安全的錯誤畫面。
- **唯讀診斷**，禁止自動格式化與寫入測試；CoreS3 官方規格為最大 16GB，兩張 128GB 卡不可宣稱已相容。
- 這是可單獨驗收的小型 MVP 功能，**不影響核心 Companion AI／寵物／通知系統、不強制插卡**。
- 具體規格見 `11_SD_STATUS_SETTINGS.md`。

## v2.3.2 → v2.3.3 最新定案（開發優先遵循）
- **自然寵物型**：寵物平常經常安靜活動，偶有文字泡泡，低頻主動說話；不追問、不要求使用者回覆。
- **AI 主導高階活動**：雲端模型決定大部分「要做什麼」，而不是逐幀操作；本機動畫／受控動作仍在 StackChan 執行。
- **寵物興趣系統**：`閱讀、研究與工作、美食、探索、藝術與創作` 五類興趣，0–100 偏好、漸進變化、防重複與記憶持久化。
- **安靜保護**：預設安靜時段 23:00–08:00（可調）、手動專注模式、原廠模式完全不受 Companion 打擾。
- **主動語音建議初始限制**：每日最多 3 次、兩次至少間隔 90 分鐘；為可修改預設值，並非經實機測試得到的最佳參數。
- **MVP 新增 MVP-19/20**：興趣演化與自然寵物的低打擾主動互動，見 `02_MVP_SCOPE.md`。
- **新文件**：`12_PET_INTERESTS.md`、`13_PROACTIVE_INTERACTION.md`、`14_RISKS_SPIKES.md`、`15_DATA_CONFIG.md`、`16_IMPLEMENTATION_BACKLOG.md`、`17_DEPLOYMENT_RUNBOOK.md`。

**請以本包 v2.3.3 內容為準。** 此文件包是設計規格，不代表已修改 GitHub、燒錄裝置或完成實機測試。

## 快速開始：交給 AI 開發
1. 將本包的 `.md` 檔案放入 Repository 的 `docs/companion/`（只新增文件，不覆蓋原廠功能）。
2. 請 Codex 先閱讀 `00_README.md`、`10_DECISIONS_v2.3.md`、`02_MVP_SCOPE.md`、`14_RISKS_SPIKES.md` 與 `08_AI_IMPLEMENTATION_PROMPT.md`。
3. 開發從 Phase 0 開始，**每階段先提交程式碼、測試、回退說明，再進下一階段**。不要一次做完全部功能，不自動燒錄。
4. 以基礎分支 `my-stackchan-01` 的已核對提交 `4a39d5114c5d8ea555444396434918db6a0f5656` 為**文件核對基線**；開始開發時再次檢查實際 HEAD，若不同需評估差異，不可強制回退使用者的更新。

## v2.3.3 文件索引與建議閱讀順序
- [`00_README.md`](./00_README.md)
- [`01_ARCHITECTURE.md`](./01_ARCHITECTURE.md)
- [`02_MVP_SCOPE.md`](./02_MVP_SCOPE.md)
- [`03_PROTOCOL.md`](./03_PROTOCOL.md)
- [`04_FIRMWARE_INTEGRATION.md`](./04_FIRMWARE_INTEGRATION.md)
- [`05_PI_SERVICES_AND_PET.md`](./05_PI_SERVICES_AND_PET.md)
- [`06_DEVELOPMENT_PLAN.md`](./06_DEVELOPMENT_PLAN.md)
- [`07_TEST_SAFETY.md`](./07_TEST_SAFETY.md)
- [`08_AI_IMPLEMENTATION_PROMPT.md`](./08_AI_IMPLEMENTATION_PROMPT.md)
- [`09_SOURCES_AND_ASSUMPTIONS.md`](./09_SOURCES_AND_ASSUMPTIONS.md)
- [`10_DECISIONS_v2.3.md`](./10_DECISIONS_v2.3.md)
- [`11_SD_STATUS_SETTINGS.md`](./11_SD_STATUS_SETTINGS.md)
- [`12_PET_INTERESTS.md`](./12_PET_INTERESTS.md)
- [`13_PROACTIVE_INTERACTION.md`](./13_PROACTIVE_INTERACTION.md)
- [`14_RISKS_SPIKES.md`](./14_RISKS_SPIKES.md)
- [`15_DATA_CONFIG.md`](./15_DATA_CONFIG.md)
- [`16_IMPLEMENTATION_BACKLOG.md`](./16_IMPLEMENTATION_BACKLOG.md)
- [`17_DEPLOYMENT_RUNBOOK.md`](./17_DEPLOYMENT_RUNBOOK.md)
- [`18_PHASE1_FIELD_ISSUES.md`](./18_PHASE1_FIELD_ISSUES.md) — Phase 1 實機問題／原因／解法
