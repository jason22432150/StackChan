# 10｜跨模組追溯、衝突與驗收對照

| 衝突／關聯 | 來源決策 | 最終處理規則 | 規格位置 | 測試 |
|---|---|---|---|---|
| Bridge 直連備援 vs 離線隱私 | #8 #48 #81 #82 | #81 優先：Coordinator 離線完全禁止 Agent 通知，Bridge 僅本地收集 | 00 §4、02 §3、05 §4 | T-SEC-01 |
| CoreS3 不留歷史 vs 查詢 | #5 #22 #47 #91 | RAM 暫態；歷史由 Coordinator／Bridge 保留、授權線上查詢 | 00 §3、03 §6 | T-PRES-01 |
| 情境隱私 vs 跨裝置授權 | #77 #78 #79 #80 | 政策全域同步，模式與短期解鎖僅限裝置，不准跨機繼承 | 05 §3 | T-SEC-02 |
| Agent 只查詢 vs 語音追問 | #14 #38 #41 #79 | 只能由授權來源事件描述狀態，不得控制 Agent 或虛構摘要 | 00 FR-05、05 §2 | T-EVT-03 |
| 回應結束 vs 任務成功 | #36 #41 #95 | 分離 event_type／evidence_level，response.completed 不推成功 | 03 §2 | T-EVT-03 |
| 狀態撤銷 vs 非同步回呼 | #87 #88 | Generation 失效即拒絕 UI／Audio／Servo 提交，ACK 不阻塞原廠 | 04 §3、05 §4 | T-SEC-03 |
| Xiaozhi 搶占 vs Coordinator 離線 | #4 #81 #89 | 對話可重評估排隊事件；離線為安全停權不可補播直到驗證 | 02 §3、04 §4 | T-XIAO-01、T-SEC-01 |
| 排隊＋合併 vs 已讀 | #5 #22 #45 #90 #91 | 合併保留原始事件；呈現與全域已讀分別記錄 | 03 §6 | T-PRES-03 |
| 分散式同步 vs 事件版本 | #6 #92 #93 #94 #96 | 來源／觀測 ID 分離、append-only、epoch、連續 ACK、衝突標記 | 03 §5 | T-SYNC-01～04 |
| 不用插件 vs 模板資產 | #54 #55 #56 #57 #58 | 模板與角色各自 JSON/YAML/素材索引；無統一 plugin manager | 06 §3 | T-ASSET-01 |
| 安全模式 vs 手動回復 | #63 #64 | 運行時自動降級可以；固件／SD 版本恢復只可手動 | 04 §8、06 §3 | T-ASSET-01 |
| 完整規格 vs 一份 Task List | #27 #30 #67 #66 | 允許多份技術規格／契約檔，開發任務**只在 09 一份** | README、09 | G1 文件驗收 |

## 其他差異需要 Phase 0 調查

1. 上游 `main.cpp` 的 Mooncake→Xiaozhi 單向切換；應確認個人分支是否已改動啟動模式。
2. 上游 `ShowNotification` 空實作；個人分支可能已有新增通知 UI。
3. 上游 `ModifyLock` bool 與 IMU Modifier 使用；須確保沒有新鎖或 Servo 行為變更。
4. 上游 HAL 音訊僅查到 `Application::PlaySound` 與 MicTest，無可信任意文字 TTS 契約；須讀實際依賴分支與平台配置。
5. 上游 ESP-IDF 版本依 `firmware/README.md` 是 v6.1；個人分支和現有環境需驗證。

## 規格變更記錄

| 版本 | 日期 | 變更 | 狀態 |
|---|---|---|---|
| v0.1 | 2026-11-16 | 由前序 96 項決策彙整規格，提供 schemas/openapi，並記錄上游 Phase 0 證據 | 候選規格，未核准 v1.0 |
