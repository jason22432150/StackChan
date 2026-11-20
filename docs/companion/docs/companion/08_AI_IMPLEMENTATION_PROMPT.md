# 08｜交給 Codex / AI 開發助手的指令（v2.3.3）

> 你可以將以下內容完整複製至 Codex；先執行 Phase 0，不要一次開發所有功能。

你是 `jason22432150/StackChan` 的 ESP-IDF 與 Raspberry Pi 整合工程師。請閱讀 `docs/companion/00_README.md` 至 `10_DECISIONS_v2.3.md`，以 `my-stackchan-01` 為基礎開發 **StackChan Companion v2.3**。

## 已確定要求
1. 這是**個人使用**專案，功能、流暢、簡單好維護優先；不引入 Docker 強制部署、Redis、企業權限系統。
2. **原廠 Xiaozhi、Launcher、Avatar、Dance、OTA 保留**；新增獨立 Mooncake Companion App，退出後回原廠。
3. Raspberry Pi 4B 單一 Python Coordinator 串接**至少兩個雲端 LLM provider**，STT/TTS 可先固定一種供應商；模型可在 Pi 端切換，不重刷設備。
4. StackChan 同時提供**觸控和喚醒詞**啟動對話；AI 播報可觸控中止，語音打斷先不做。
5. Companion 為預設可選的主要模式，有 Launcher 退回與離線保護。
6. **只在 Companion 開啟時顯示／播報 Agent 通知**；原廠模式可由 Pi 記錄事件，但絕不打擾設備。
7. 日常寵物活動**主要由雲端 LLM 自主決定**；限制在安全動作白名單、設定頻率/費用上限、離線規則備援。
8. SQLite 保存偏好、寵物關係與重要事件，可查看/修改/刪除；不預設永久儲存原始錄音。
9. Pi 用一張 128GB microSD；第二張保留，StackChan 不依賴它。
10. **永久禁止新增任何 eFuse 寫入**；不啟用要寫 eFuse 的 Secure Boot/Flash Encryption provisioning。

## 開始前先檢查
- 當前 branch / HEAD / dirty files 與 `my-stackchan-01` 是否一致。不要直接改主分支。
- 閱讀 `firmware/main/main.cpp`、`firmware/main/apps/app_template/`、`firmware/main/apps/app_ai_agent/`、`firmware/main/hal/audio.cpp`、`firmware/main/hal/hal_ws_avatar.cpp`、`firmware/main/CMakeLists.txt`。
- 任何 API 與原始碼有出入時，以當前實際原始碼為準；先提出差異與最低影響修正方案，**不要憑空編造 SDK API**。

## 本次只做 Phase 0
1. 若開發環境權限允許，從 `my-stackchan-01` 建立 `feature/stackchan-companion`；避免覆蓋現有變更。
2. 加入可開啟／退出的 `AppCompanion` 空殼與 Launcher 註冊，不改 `AppAiAgent`。
3. 加入 Pi Python 專案骨架、Provider 介面（先 mock）、SQLite schema 草案、基礎測試；**本階段不要真的呼叫雲端模型，也不要實施自動燒錄**。
4. 依實際環境執行 `idf.py build` 與 Python tests（執行每個命令前說明作用）。
5. 回報差異清單、功能檢查、測試數據、未實機驗證處及下一個階段。

## 後續階段
依 `06_DEVELOPMENT_PLAN.md` 逐步建立 LAN、雙喚醒與語音、多模型、AI 寵物自主、開機主模式、通知模式隔離，再做 Agent Bridge。每個階段完成後更新程式、測試、協定與文件。

## 每次完成的報告格式
- 已做事項／改動檔案與原因。
- 實際執行的命令、命令目的、結果（不能把未跑過的測試宣稱通過）。
- 是否修改原廠功能、如何驗證回退。
- eFuse 寫入確認：**未新增、未執行任何寫入**。
- 待確認風險及下一個階段。

## 補充實作任務：StackChan microSD 設定頁
> 在既有 `my-stackchan-01` 韌體中追加 `SETUP → Device → Storage / microSD`。先閱讀 `11_SD_STATUS_SETTINGS.md`，依 ESP-IDF 6.1 實際驅動做**唯讀掛載及容量查詢**。不得使用格式化、寫入測試、eFuse 寫入；無卡、不支援格式、128GB 無法掛載時都要顯示清楚且不阻塞的錯誤狀態。先完成編譯與靜態檢查，再提出硬體實測步驟。不得聲稱 128GB 已通過實測。

## v2.3.3 需求不得漏掉
- `12_PET_INTERESTS.md`：五種興趣、偏好成長、防重複、離線規則、SQLite 持久化；須納入 MVP。
- `13_PROACTIVE_INTERACTION.md`：自然寵物型、低打擾、靜默時段、專注模式、每日主動語音上限、無回覆不追問；須納入 MVP。
- `14_RISKS_SPIKES.md`：高風險實測先行，**原廠 Mooncake → Xiaozhi 非無縫雙行程**，不可自行推論已支援。
- `15_DATA_CONFIG.md`：資料表與配置格式為示例合約，需寫測試保證資料遷移及設定相容。
- `16_IMPLEMENTATION_BACKLOG.md`：每階段有明確驗收與禁止超前開發。
- `17_DEPLOYMENT_RUNBOOK.md`：所有需要使用者執行的命令都應說明用途、效果、風險；不要求在開發階段自行燒錄。

**這次任務先做 Phase 0**。請只建立獨立分支、建立新 App 空殼與 Pi skeleton、提供 build/test 成果；不得連外訂購服務、不得硬編 API 金鑰、不得更動原廠 Xiaozhi 核心、不得執行任何 eFuse 寫入、不得自動刷機或格式化任何 microSD。
