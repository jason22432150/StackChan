# StackChan Companion v2.3.3 — 給 Codex 的最短起始指令

請先完整閱讀 `docs/companion/` 下 `00_README.md`、`10_DECISIONS_v2.3.md`、`02_MVP_SCOPE.md`、`14_RISKS_SPIKES.md`、`16_IMPLEMENTATION_BACKLOG.md`、`08_AI_IMPLEMENTATION_PROMPT.md`。

本次只執行 **Phase 0**：核對目前分支及 HEAD、確認既有改動、不破壞原廠功能；在獨立開發分支新增 Mooncake `AppCompanion` 空殼與 Raspberry Pi Python Coordinator 骨架。不能假設目前已存在完整音訊串流或喚醒詞。保留 `AppAiAgent`/Xiaozhi、Launcher、原廠 OTA。**絕對禁止任何新增 eFuse 寫入、格式化 microSD、未經使用者同意自動燒錄韌體。**

若資料不足，先讀原始碼、做最小可驗證測試，再提交一份包括修改檔案、理由、測試、未驗證點、回退策略的報告。不要一次性實作後續全部功能。

專案原始碼：https://github.com/jason22432150/StackChan/tree/my-stackchan-01
