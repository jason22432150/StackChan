# 06｜開發路線圖（MVP 與後續）

> **同一個 MVP 不代表一次性寫完。** 依 Phase 逐個完成及驗收，實機風險越高越要先做小型技術驗證。

## Phase 0 — 只讀基線與新 App 空殼
- 檢查當前 HEAD、git status、ESP-IDF 版本、現有 builds、eFuse 安全規則。
- 建立 `feature/stackchan-companion` 分支；保留主要分支不修改。
- 加入 `AppCompanion` 空殼，可從 Launcher 開啟/退出；Pi Python skeleton + 單元測試。
- 驗收：firmware build、Python 測試；原廠 App/AI 入口保留。**不自動燒錄**。

## Phase 1 — 連線、UI 與動作
- Pi WebSocket、配對與重連、`hello/heartbeat/ack`；文字、表情、STOP、限位轉頭及離線提示。
- 在 Companion App 活動期間才允許顯示指令；退出後不蓋原廠 UI。
- 驗收：往返控制、斷線恢復，單次動作不衝突。

## Phase 2 — 雙喚醒與雙向音訊（最高技術風險）
- 驗證 ESP32-S3 Audio Codec 所有權、聲音編碼及喚醒詞位置（設備端或 Pi）；將選擇與測試結果寫入文件。
- 實作觸控啟動與**喚醒詞啟動**；Pi STT／LLM／TTS 回 StackChan；觸控中止播放、取消過時回應。
- 驗收：20 輪觸控問答、喚醒詞 10 次測試、觸控中止、切原廠模式音訊不衝突。

## Phase 3 — 多模型與 AI 自主寵物
- 實作 Provider A/B 真正適配器（無金鑰可 mock；有金鑰需驗證兩個真實服務），切換 active provider；STT/TTS 可先固定。
- 實作 AI 寵物 planner、白名單動畫、冷卻與本機規則 fallback、寵物狀態／偏好／重要事件 SQLite。
- 驗收：模型切換不刷機；AI 在線時選大部分日常活動；離線退回待機；重啟資料保留。

## Phase 4 — 主要模式、回退與 MVP 完成
- 新增 `boot_mode=companion|launcher`，完成開機進 Companion、退出、原廠 Xiaozhi 相容性驗證、離線保護。
- MVP 模式隔離：Pi 模擬 Agent 事件時，原廠模式沒有 Companion 通知；進入 Companion 可看到未讀摘要。
- 完成 `02_MVP_SCOPE.md` P0 各項逐條驗收；更新延遲、記憶體與電費／API 費用測試結果。

## Phase 5 — Agent 通知功能（P1）
- 先接 Codex 官方/可靠完成事件，再看 Cursor、ChatGPT、Grok 的可用能力。
- Pi 去重、可信度、對話期間排隊、通知只在 Companion 顯示；語音追問事件摘要可拆出後續工作。
- 驗收：非 Companion 不推播；對話不中斷；完成和失敗不被 UI 推測誤判。

## Phase 6 — 流暢與體驗優化（P1/P2）
- 分段 TTS、增量字幕、進階表情動畫、語音打斷（回聲消除與全雙工）、設定頁、Pi 獨立更新 UX。
- 提升喚醒詞辨識品質與耗能、擴充模型與活動素材。

## 每階段交付內容
1. 修改的檔案、原因、實測過的測試和結果。
2. 相容性與性能變化：記憶體用量、平均反應延遲（測量後才寫數字）。
3. 協定／README 與 API 設定範本同步更新。
4. 風險、回退方法、eFuse 零寫入確認。

## 常用開發命令（每個都需說明原因）
| 命令 | 為什麼／會發生什麼 |
|---|---|
| `git status` | 檢查檔案修改與目前分支，不會修改程式碼 |
| `git switch -c feature/stackchan-companion` | **確認位於正確基礎分支後**建立獨立開發分支；不改主分支歷史 |
| `idf.py build` | 在 `firmware/` 編譯並檢查錯誤；不燒錄裝置且不寫 eFuse |
| `python -m pytest` | 在 Pi Python 專案執行測試；正常單元測試不接硬體 |
| `sudo systemctl restart stackchan-companion` | 更新 Pi 程式後重啟已安裝服務；會中斷當時對話，再由 StackChan 重連 |

任何燒錄韌體命令都不是自動執行步驟。先確認 USB Port、Flash layout、映像、備份及是否會影響安全設定，並由使用者明確知悉與批准。

## 獨立子任務：SD 狀態頁（可與 Companion 基本通訊後平行開發）
**SD-Phase 0（查證）**：確認 CoreS3 SPI 腳位、總線使用者、ESP-IDF 6.1 FATFS 驅動依賴；對 128GB 相容性只做風險標示。

**SD-Phase 1（唯讀 HAL）**：實作一次性的 SD 初始化及保守狀態查詢；未插卡或掛載失敗不影響其他功能，禁止格式化與寫入。

**SD-Phase 2（設定 UI）**：在 `SETUP → Device → Storage / microSD` 建立總容量、已使用、剩餘、使用率、狀態與重新檢查 UI。

**SD-Phase 3（測試）**：依 `11_SD_STATUS_SETTINGS.md` 的 SD-01～SD-08 在無卡、已知相容卡、128GB 卡及讀取失敗時測試，不將 128GB 成功掛載列為必達目標。

## v2.3.3 Phase 細化：把興趣與自然寵物納入 MVP
- **Phase 0**：建立新 App 空殼／Pi 骨架、加上測試工具與本文件；先不刷機。
- **Phase 1**：連線、表情／文字／安全動作／本機動畫執行器、斷線與 stop。
- **Phase 2**：音訊路線技術驗證、雙喚醒、觸控打斷、STT→LLM→TTS；先用假 Provider 無費用測試，再連真 API。
- **Phase 3**：雲端 LLM A/B、SQLite 持久記憶、五類興趣分數、AI 高階活動決策、Planner 輸出白名單及規則備援。
- **Phase 4**：自然寵物主動互動的頻率控制、專注模式、安靜時段、原廠切換、開機模式、防打擾、microSD 設定頁、MVP-01～MVP-20 全項驗收。
- **Phase 5（P1）**：真實 Codex 原生 hook/可靠事件，接著逐一評估 Cursor/ChatGPT/Grok；只有 Companion 模式播放通知。
- **Phase 6（P1/P2）**：分段 TTS 與低延遲 UX、進階動畫、語音打斷、更多興趣與細緻記憶。

**交付閘門**：每階段附 `修改檔案清單 / 自動測試 / 實機測試 / 未完成項 / 回退方式 / 是否觸及 eFuse` 六項；不可因模擬測試通過就聲稱硬體驗收完成。詳細任務見 `16_IMPLEMENTATION_BACKLOG.md`。
