# 00｜完整系統規格（候選基準 v0.1）

## 1. 願景與使用者故事

使用者在 Windows、macOS、Linux 電腦上使用 Codex、Cursor、ChatGPT、Grok 等原生或網頁 AI Agent。當 Agent 開始、執行、等待使用者、回應結束、確認成功、失敗、取消時，電腦上的 Bridge 以適當 Adapter 偵測事件，安全地送往 Coordinator，由 Coordinator 對符合規則的 StackChan CoreS3 下發通知。Mew 可用全身動畫、表情、Servo、音效／受控 TTS 回應；原廠 Xiaozhi 進行語音對話時不得搶占。使用者可對 StackChan 語音追問已獲授權的原始任務資訊，不能遙控遠端 Agent。

典型路徑：Codex 原生 Hook → Bridge 事件日誌 → Coordinator 政策／排程 → CoreS3 顯示 Mew 動畫 → 對話結束後補播／語音查詢 → 呈現 ACK 與唯讀 Dashboard。

## 2. 驗收成果（Product Outcomes）

- **O1 可靠接收**：可以追蹤四類以上的 Agent 整合方式；MVP 優先已驗證 Codex／Cursor 來源，其他依 Adapter 能力分級。
- **O2 任務語義準確**：`response.completed` 與 `task.succeeded` 明確不同，低可信推測標記不確定，不捏造任務成功。
- **O3 使用者體驗**：通知動作不破壞 Xiaozhi；多筆通知能合併、限速、排隊、智慧補送。
- **O4 安全**：Coordinator 不可用或隱私政策無效時裝置不呈現任何 Agent 通知；立即撤銷已呈現內容及通知資源。
- **O5 可追溯**：穩定 Event ID、Bridge Observation ID、追加式修正、獨立裝置回報、全域已讀版本化。
- **O6 多平台**：Bridge 原生 Windows/macOS/Linux；Coordinator 可部署原生或 Docker／NAS；CoreS3 多裝置。
- **O7 Mew**：全身角色，SD 素材優先，圖層／Spritesheet／Servo／音效動畫；失敗時內建角色降級。

## 3. 功能需求

### FR-01 Agent Adapter

每一 Adapter 公開 `source_kind`、`capabilities`、`event_semantics`、`confidence`、`permissions`、`observed_at` 及可取得的原生 ID。優先 Hooks／API，其次瀏覽器 Extension，最後有授權的 UI Monitor。不得繞過應用權限或私自蒐集 Prompt、對話全文、憑證。UI 監聽低證據事件不得使用成功／失敗專用音效或角色動畫。

### FR-02 Bridge

每台使用 Agent 的電腦常駐一個 Bridge：本機 Adapter 管理、來源別身分、事件格式驗證、Outbox 與 SQLite 短期保存、同步游標、節流去抖、來源證據分級、跨平台設定、CLI＋Tray GUI＋Local Web。Bridge 不應代替 Coordinator 規避隱私；Coordinator 離線時 **僅保留事件，絕不可直送 Agent 通知至 CoreS3**。

### FR-03 Coordinator

提供身分配對、政策版本、分層設定、事件匯入、來源因果對帳、任務投影、通知排程、裝置路由、全域已讀、派送憑證、唯讀 Dashboard、診斷匯出、資產與模板管理。風險區隔：管理／匯出 API 需另行授權；無 Agent 遠端執行功能。

### FR-04 CoreS3 通知

只接收 Coordinator 已核准且目前有效的 NotificationIntent；本機維持 RAM 暫態。接收／顯示／音訊／動作經 NotificationController 和 ResourceArbiter。支援多裝置、角色優先、觸控、狀態指示、Xiaozhi 搶占與恢復。不得保存通知歷史到 Flash／SD。

### FR-05 Xiaozhi／語音追問

原廠語音、音訊與裝置功能優先。對話期間 Agent 通知排隊，正在播放的通知安全中斷，對話後重新檢查 Coordinator、隱私、TTL 和狀態。查詢結果只能依據可獲得原始事件；敏感資料須分級並有可信確認。不得因語音指令取得遠端 Agent 控制權。

### FR-06 Mew 與角色引擎

支援 Mew 全身、表情、待機、眨眼、嘴巴、通知動作；動畫時間軸可包含影格／圖層／Servo／音效；SD 卡優先、固件備援、授權 LAN 更新。素材轉檔及最佳化在 PC 端做，裝置端以不阻塞 Audio 為首要；採 LVGL 模擬器測 UI，但實機仍必驗收。

### FR-07 UI 與 Dashboard

核心通知視圖支持浮層／卡片／歷史瀏覽（Coordinator 在線查詢）、分群與輪播、分級優先、觸控手勢、勿擾。Dashboard 唯讀 Agent 狀態／歷史，允許通知已讀與本系統設定管理，但不能向 Agent 傳新指令。裝置只有暫態卡片，不寫本機通知歷史。

### FR-08 安全隱私

單使用者環境，但依 Bridge／Device／Session 使用最小權限憑證。全域政策同步、裝置情境與解鎖獨立、可手動覆寫一般環境判斷但不覆寫安全底線；隱私政策同時涵蓋螢幕與 TTS。未知場域以保守呈現。Coordinator 不可用立即 Fail-Closed，無備援直送。禁止預設開啟攝影機、聲紋辨識、持續環境監聽。

### FR-09 同步與生命週期

事件追加式、資料庫短期保存，Bridge 分世代序號與連續 ACK 游標，冪等導入；全域已讀有版本，各裝置呈現獨立；事件證據更新為追加式更正，已呈現錯誤通知需留更正關聯。TTL 與資料保留期限分開。

### FR-10 維護與部署

簡單錯誤紀錄與一鍵遮蔽診斷，不建大型監控系統。設定分層（全域／Device／Bridge／Agent／Project／Event）、版本與可選還原；軟體分級升級，韌體燒錄及手動回復需人類授權。支援 mDNS 發現／手動 IP、LAN/VPN/可選遠端中繼；不要把 CoreS3 直接暴露於 Internet。

## 4. 核心設計不變式（MUST）

1. Coordinator 失聯、身份驗證失敗、政策失效 => Agent 通知功能「Fail-Closed」。
2. 安全中斷撤銷顯示權限優先於等待各子系統 Cancellation ACK；Xiaozhi 不得被通知取消流程阻塞。
3. 永不因 `response.completed` 或閒置而自行宣稱 `task.succeeded`。
4. 同一來源事件的重送採冪等，跨來源模糊觀測禁止擅自強行去重。
5. `AgentEvent`、`NotificationIntent`、`PresentationReceipt`、全域 `ReadState` 分離。
6. `Presented` 不等於 `Read`，`Read` 不等於每台裝置已呈現。
7. 所有通知 UI、TTS、Servo 工作回呼在提交資源時檢查有效 Generation 與授權。
8. 事件歷史僅在 Bridge／Coordinator 端短期持久化，CoreS3 不持久化歷史。
9. 通知音訊不得競爭或直接繞過原廠 Xiaozhi AudioCodec／Application 的使用權。
10. 手動設定不得解除不可覆寫敏感資訊底線；短期解鎖不可跨裝置繼承。

## 5. 非功能需求與未定量門檻

安全：預設拒絕；連線異常限界；不暴露憑證；所有輸入驗證大小與類型。可靠性：At-Least-Once 傳輸、冪等效果、順序缺口處理、重啟復原、可補送。效能：禁止 UI／Audio 任務做網路等待或大量 SD 解碼；佇列與記憶體上限從實機量測設定，不預先承諾 FPS／延遲。跨平台：Win 首先驗收，macOS/Linux 持續保留相容設計。可維護：契約版本基準、變更紀錄、單一開發清單與風險分級人工 Gate。

## 6. 範圍分期

- **Phase 0 (先行門檻)**：核對使用者分支、讀取 Xiaozhi 音訊依賴與原始碼、確認 LVGL／Servo／SD／Codex／Cursor 來源能力，留下實證。
- **MVP 1 (必要)**：Bridge、Coordinator、SQLite、事件契約、基本安全配對、Fail-Closed、單 CoreS3 顯示＋基本 Mew 反應、原廠 Xiaozhi 不受損、基礎收據回報、Windows＋實機驗收。
- **MVP 2**：完整離線智慧補送、多裝置與已讀、Browser/UI Adapter 分級、基本唯讀 Dashboard、語音查詢最小可行整合（以 Phase 0 可行性為前提）。
- **擴充**：多角色、全身時間軸動畫、SD 上傳、Web 視覺編輯器、跨平台、遠端安全連線、複雜情境隱私與診斷。

分期不代表取消既有已確認需求。MVP 未具完整情境感知時，必須使用保守隱私預設，且不得在聲稱功能完成前跳過 Gate。

## 7. 驗收口徑

所有產品目標需綁定測試案例及實證：最小 MVP 需完成真實 Agent 事件、Bridge 寫入與重試、Coordinator 正常／離線／恢復、CoreS3 呈現／中斷、Xiaozhi 對話不受干擾、Servo 安全、SD 損壞降級、遮蔽與憑證安全。硬體驗收不要求建立精密硬體實驗室；具體性能上下界在 Phase 0／性能基準量測後填寫。

## 8. 文件發行規則

本版是候選規格 `v0.1`，所有新增 API／任務均須參照決策編號、風險、測試證據。影響安全、重寫原廠音訊、燒錄韌體、Merge 主分支、刪除資料的工作均需要明確人工授權。未授權不進行實作。
