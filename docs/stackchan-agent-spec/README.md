# StackChan AI Agent 通知平台 — 技術規格交付包

**版本**：v0.1 候選基準（Planning Draft）　**日期**：2026-11-16　**語言**：繁體中文

**基礎專案**：https://github.com/jason22432150/StackChan ；原廠上游：https://github.com/m5stack/StackChan

> 這是**規劃與開發交接文件**，不是已實作的系統，也未修改任何使用者 Git Repository、未進行燒錄或實測。原始碼證據僅以可讀取的 M5Stack 上游為準，使用者分支不可讀，須在 Phase 0 進行差異比對。接口與資料表是**候選契約**，不得視為已存在的 API。

## 閱讀與交付順序

1. `docs/00_MASTER_SPEC.md`：完整產品／系統規格，正式範圍與不變式。
2. `docs/01_DECISIONS_01_96.md`：96 項已確認決策的追溯索引；#97～99 為後續推薦的候選細化，**未列入已確認的 96 項**。
3. `docs/02_ARCHITECTURE.md`：部署、模組、時序與故障路徑。
4. `docs/03_EVENTS_API_DB.md`：Event、Intent、Receipt、API、SQLite、同步與狀態機。
5. `docs/04_FIRMWARE_XIAOZHI.md`：CoreS3／FreeRTOS／LVGL／Xiaozhi／Servo 接入方案。
6. `docs/05_SECURITY_PRIVACY.md`：配對、資料最小化、情境隱私、離線 Fail-Closed。
7. `docs/06_MEW_ASSETS.md`：全身 Mew、SD 卡優先、動畫與角色素材。
8. `docs/07_TEST_ACCEPTANCE.md`：契約／整合／安全／實機測試與 Gate。
9. `docs/08_RISKS_AND_UNKNOWNS.md`：風險登錄與技術驗證要求。
10. `docs/09_DEVELOPMENT_CHECKLIST.md`：**唯一一份開發任務 Markdown Checklist**，其他文件不建任務清單。
11. `docs/10_TRACEABILITY.md`：跨模組決策追溯與衝突處理。
12. `docs/11_EVIDENCE_SOURCES.md`：已檢查的上游原始碼路徑、觀測與限制。
13. `contracts/agent-event.schema.json`、`notification-intent.schema.json`、`presentation-receipt.schema.json`：草案 JSON Schemas。
14. `contracts/openapi.yaml`：HTTP API 提案；不是已部署端點。
15. `StackChan_規格總覽.pdf`：非工程背景快速總覽；**詳細規格以 Markdown 套件為準**。

## 規格狀態定義

- **CONFIRMED**：使用者已確認的需求方向，不代表程式已存在。
- **PROPOSED**：為落地需求而提出的技術設計，可於 Phase 0 檢查後調整。
- **UPSTREAM-VERIFIED**：檢查過 M5Stack 上游特定原始碼，未必與使用者分支一致。
- **UNVERIFIED**：沒有來源或實測保證，須先驗證。
- **BLOCKED**：實作前必須解決的前置門檻。

## 重要範圍約束

- 單一使用者；多 Bridge、多 CoreS3；AI Agent 僅通知及唯讀查詢，禁止遙控 Agent。
- 原生 Xiaozhi 優先；Xiaozhi 對話期間排隊；通知 TTS 與語音追問不能在未驗證音訊路徑前宣稱可用。
- Coordinator 失聯或政策無法驗證時，CoreS3 **完全禁止 Agent 通知**，覆蓋早期 Bridge 直連備援想法。
- CoreS3 不持久化通知歷史；Bridge、Coordinator 採短期保存；預設天數尚待設定。
- 不呼叫額外 AI 來捏造摘要；僅依原始事件有證據的事實描述。
- 角色優先 SD 卡；原廠／內建素材備援；不建立通用 Plugin Marketplace。
- 韌體／素材回滾為使用者明確授權的手動作業，安全模式與運行時降級不等同自動回滾。

## 完成度

規格屬於 **v0.1 候選基準**，尚未執行：使用者分支差異、音訊控制與 TTS、CoreS3 硬體驗證、OpenAPI 端點實作、性能實測、完整人工逐項決策重新驗證。不得當成完成的 v1.0 建置成果。
