# 11｜原始碼證據、調查紀錄與官方來源

## 1. 來源分層

- **使用者指定基礎**：https://github.com/jason22432150/StackChan ，本輪 GitHub 工具未取回其內容；分支對照為 P0 前置門檻。
- **上游實證**：https://github.com/m5stack/StackChan ，使用 GitHub 連接器讀取相應路徑中的完整程式或片段。
- **官方平台說明**：ESP-IDF、LVGL、SQLite、JSON Schema、OpenAPI、RFC 9562。平台文件不代表本案韌體已符合。

## 2. 上游原始碼鏈接與結論

| 證據路徑 | 已讀到的具體事實 | 不可推導的部分 |
|---|---|---|
| [main.cpp](https://github.com/m5stack/StackChan/blob/main/firmware/main/main.cpp) | Mooncake app loop 後卸載 apps、DestroyMooncake、startXiaozhi | 通知服務已存在 |
| [app_ai_agent.cpp](https://github.com/m5stack/StackChan/blob/main/firmware/main/apps/app_ai_agent/app_ai_agent.cpp) | onOpen 請求進入 Xiaozhi | 同步音訊獨占功能 |
| [hal.cpp](https://github.com/m5stack/StackChan/blob/main/firmware/main/hal/hal.cpp) | `stackchan` 更新任務，20ms delay、LVGL guard、非 idle 的 100ms delay、reminder 通知 UI callback | 鎖延遲是已發生的 Bug 或完成了通知功能 |
| [hal_bridge.h](https://github.com/m5stack/StackChan/blob/main/firmware/main/hal/board/hal_bridge.h) | `is_xiaozhi_idle`, `is_xiaozhi_ready` 和 LVGL lock 等函式 | Idle 代表 Audio lease 有效 |
| [hal_bridge.cc](https://github.com/m5stack/StackChan/blob/main/firmware/main/hal/board/hal_bridge.cc) | `app_play_sound`→`Application::PlaySound` | 可以安全播放任意 TTS |
| [stackchan_display.cc](https://github.com/m5stack/StackChan/blob/main/firmware/main/hal/board/stackchan_display.cc) | Avatar/Modifier、`SetStatus()`、`ShowNotification()` 空實作、LVGL Port | 有完整通知 Presenter |
| [motion.cpp](https://github.com/m5stack/StackChan/blob/main/firmware/main/stackchan/motion/motion.cpp) | `move*`, `stop`, `setModifyLock` bool | `ModifyLock` 是 Mutex 或 `stop` 物理即停 |
| [imu.h](https://github.com/m5stack/StackChan/blob/main/firmware/main/stackchan/modifiers/imu.h) | IMU Modifier 會鎖定／恢復 Avatar／Motion ModifyLock | 已有跨任務 Servo Resource Arbiter |
| [audio.cpp](https://github.com/m5stack/StackChan/blob/main/firmware/main/hal/audio.cpp) | Mic 測試會直接 EnableInput／Output／OutputData | 該測試路徑可作通知音訊整合 |
| [firmware README](https://github.com/m5stack/StackChan/blob/main/firmware/README.md) | 上游 README 標示 ESP-IDF v6.1 與 host-side tests | 使用者分支也一定是同一版 |

## 3. 官方標準與 API

- https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/freertos.html
- https://docs.lvgl.io/
- https://www.sqlite.org/docs.html
- https://www.sqlite.org/lang_upsert.html
- https://json-schema.org/
- https://spec.openapis.org/oas/latest.html
- https://www.rfc-editor.org/rfc/rfc9562.html
- https://owasp.org/www-project-application-security-verification-standard/

## 4. 稽核待辦證據（尚非實測）

Phase 0 應記錄個人分支 HEAD SHA、對照上游 SHA、`firmware/repos.json` 實際依賴版本、依賴 patch 適用性、Xiaozhi Session API、實機 FreeRTOS Task Dump、AudioCodec Ownership、Servo 物理限制、CoreS3 記憶體量測、真實 Codex/Cursor Hook payload。未具證據，不得在規格或 PR 自動升級為 VERIFIED。

## 5. P0-07 Agent 事件與來源授權（2026-11-16）

本機辨識到 Codex CLI `0.156.1` 與 Cursor IDE `3.30.14`。版本查詢確認安裝基準，事件支援以官方文件核對，Adapter 轉換以本機測試覆蓋。兩個客戶端的真實 Hook 投遞仍待端到端驗證。

| 來源 | 支援與證據界限 | 最小授權 |
|---|---|---|
| Codex Hooks | `Stop` 是回合停止點，Hook 可以要求回合繼續。Bridge 目前記為 `response.completed`／`observed`，涵義限當次回應。官方另列 `Interrupt`，現有 Adapter 會降為 `observation.uncertain`／`unknown`。舊式 `notify` 的 `agent-turn-complete` 是獨立相容來源。 | 使用者或管理員核可 Hook。Bridge 僅觀測事件，Hook 回傳應符合官方協定並避免續跑、批准命令或修改輸入。部署前仍須驗證目前 CLI 的 stdout 與 Hook 包裝介面相容。 |
| Cursor IDE Hooks | 1.7 首次提供 Hooks beta，當前文件提供 `stop`、`subagentStop`、session 與工具事件。IDE `stop.status` 的 `completed`、`error`、`aborted` 分別代表回應完成、失敗及取消。雲端 Agent 的唯讀前期不執行 Hooks，且其中 `sessionStart`、`sessionEnd` 等事件不可用。1.7 的引入紀錄不足以確立各事件的最低版本。 | 特定專案或經授權的作用域，讀取 Hook metadata。Hook 的工具控制與自動續跑輸出不在通知授權內。 |
| ChatGPT／Grok 官方面 | 已核對 ChatGPT 的帳戶資料匯出與 Grok 的產品文件、xAI Responses API。這些文件未建立可供本案讀取既有消費者聊天的即時 Agent 生命週期事件。 | 授權以實際產品介面、帳戶與工作區為限。資料匯出及 API 憑證各自適用於其介面。 |
| ChatGPT／Grok 瀏覽器 | P4-02 候選。只從使用者選取的分頁觀察可見狀態；中斷、分頁休眠、畫面停更與重新整理均可能造成誤判。最多 `inferred`；缺證時為 `unknown`。 | 由使用者啟用當前分頁，例如 Chrome `activeTab`，再限制來源網域與可見狀態欄位。Cookies、登入資料、對話歷史、全文 DOM 及其他分頁不在授權內。 |
| ChatGPT／Grok 桌面 UI | P4-02 候選。畫面或無障礙狀態最多提供 `inferred`，失焦、遮蓋或場景不明時降為 `unknown`。兩者皆無已驗證的本機 Adapter。 | 另行取得指定 app／視窗的可見狀態讀取授權，限使用者啟用的工作階段。 |

Adapter 回歸確認回應完成事件不會升級為 `task.succeeded`，未登錄的 ChatGPT UI Adapter 會被拒絕。現有兩個 Hook 白名單仍含 `cwd`，接入正式資料前應核查路徑最小化與遮蔽。Cursor `subagentStop` 對缺失／未知狀態會回報 `response.completed`，需要以真實版本樣本驗證，避免把異常 payload 當成完成。此次只做能力稽核，沒有啟用 Hook、瀏覽器或桌面 UI 收集。

- Codex 事件、信任與舊式通知。[Hooks](https://learn.chatgpt.com/docs/hooks) · [設定參考](https://learn.chatgpt.com/docs/config-file/config-reference)
- Cursor 引入版本與事件範圍。[1.7 Changelog](https://cursor.com/changelog/1-7) · [Hooks](https://prod.cursor.com/docs/hooks)
- 帳戶、API 與瀏覽器權限範圍。[ChatGPT 資料匯出](https://help.openai.com/en/articles/7260999-exporting-your-chatgpt-history-and-data) · [Grok 網站與 Apps](https://docs.x.ai/grok/faq) · [xAI Responses](https://docs.x.ai/developers/rest-api-reference/inference/responses) · [Chrome activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab)
