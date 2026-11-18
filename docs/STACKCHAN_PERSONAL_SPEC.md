# StackChan Personal Edition｜精簡開發規格 v0.5

> **本文件為唯一當前開發規格**。以 v0.4 個人版為基礎刪去非必要的企業級規範與歷史相容需求。尚未實作、部署或通過實機驗收。本文件不能取代實際原始碼調查。若與舊版 v0.1～v0.4 內容衝突，以本文件為準；唯獨已確認的不可逆硬體安全底線不得弱化。

## 1. 我想做什麼

把一台 M5Stack StackChan CoreS3 變成桌面 Agent 通知機器人。當電腦上的 Codex／Cursor 有**可驗證**的工作狀態變化時，StackChan 顯示 Mew 表情／動畫並輕微轉頭，必要時播放提示音。平常有眨眼、睡覺、閱讀、玩耍等待機動作。**保留原廠 Xiaozhi 對話，對話時不插嘴。**

首版只需可靠完成 **Codex → Bridge → Raspberry Pi Coordinator → StackChan 通知**。Cursor、豐富 Mew 素材、語音追問、ChatGPT/Grok 為第二階段；能驗證後再加入，不能假裝已支援。

## 2. 固定設備與架構

```text
Windows 電腦 (Codex/Cursor + Bridge)
          │  有身份驗證的加密連線
          ▼
Raspberry Pi 4B (唯一正式 Coordinator)
Raspberry Pi OS Lite 64-bit + Docker Compose
SQLite 儲存、通知排程、簡單 Dashboard
          │  有身份驗證的加密連線
          ▼
M5Stack StackChan CoreS3
Xiaozhi + LVGL/Mew + Servo + 通知
```

- 128GB microSD **先給 Raspberry Pi 開機與 SQLite**；若 CoreS3 要獨立 SD 素材，需另備卡；首版使用韌體內建少量動畫即可。
- Bridge 必須在使用 Agent 的電腦上。Pi 停機時 Bridge 可暫存事件，**不准直接對 CoreS3 發通知**。
- 個人使用、一個管理員、一台 CoreS3；不做多使用者、多裝置群播、公開網際網路服務。

## 3. 首版必做功能

1. **Agent 事件監聽**：先 Codex 官方 Hook/API（以實際專案及工具版本查證）；能收到開始、回應結束、等待或成功/失敗的哪一種，就誠實標示哪一種。`response.completed` **不等於** `task.succeeded`。
2. **Bridge**：只蒐集必要事件，不蒐集密碼、API Key、完整 Prompt；SQLite Outbox 儲存未送達事件；重試時靠唯一 `event_id` 去重。
3. **Pi Coordinator**：在 Pi 4B Docker Compose 常駐、SQLite 保留短期通知歷史、單一簡易管理頁、FIFO 佇列／重要事件優先／TTL；收到後先可靠儲存再確認 Bridge。
4. **安全配對**：首次由使用者在可信管理介面確認短效一次性配對碼；每台 Bridge/CoreS3 具有**獨立、可撤銷的 Token**，使用 TLS 並驗證 Pi 身份。不能只相信 IP、mDNS 或 Wi-Fi；管理介面不開放公網。
5. **CoreS3**：只接受已配對 Pi 的有效通知；LVGL 顯示通知和 Mew 基本表情；安全的輕量 Servo 動作；簡單提示音經過 Xiaozhi 音訊相容性驗證才啟用。
6. **Xiaozhi 與安全中斷**：Xiaozhi 對話優先；通知排隊，已開始的通知在需要時取消；Pi 失聯、Token 被撤銷、通知過期時取消通知、清掉內容並停止通知動作；舊回呼不可讓通知重新出現（Generation Token／等效機制）。CoreS3 不把 Agent 通知歷史寫入 Flash/SD。
7. **事件可信度**：`Confirmed`（來源確認）、`Observed`（觀察到回應或狀態）、`Unknown`（不明）。只有真正具備來源成功證據的事件才可以說「任務成功」。不使用 AI 推測補完事件內容。

## 4. 絕對不可放寬：eFuse 與燒錄

**開發及測試期間禁止新增任何 ESP32-S3 eFuse 寫入。**

- 不可執行任何 eFuse 燒寫指令/API，或自行啟用 Secure Boot、Flash Encryption、UART/JTAG/USB 永久限制。
- 不可燒入會在**首次或後續開機**自行寫入 eFuse 的 Bootloader／韌體。
- **不得關閉、繞過或降低出廠已啟用的安全保護**；如果原有安全設定使自訂韌體無法安全燒錄，立即停止。
- 每次 CoreS3 燒錄與 OTA **必須由使用者針對該次操作明確批准**；批准燒錄也不代表批准修改 eFuse。
- 燒錄前須唯讀核對裝置現有 eFuse、`sdkconfig`、Bootloader、依賴 Patch、首次開機行為；若無法證明不會新增 eFuse 寫入，**禁止燒錄**。
- AI 不得自行格式化現有 128GB 卡、刪除使用者資料、修改 Git 主分支或推送遠端，除非另外取得操作授權。

## 5. 技術整合注意事項

目前只對 **M5Stack 上游** `m5stack/StackChan` 做過部分原始碼調查，必須再核對你的 `jason22432150/StackChan` 實際版本。

- 原廠 `firmware/main/main.cpp` 會從 Mooncake 切到 Xiaozhi 常駐流程；通知不可只做成會被卸載的 Mooncake App。
- `firmware/main/hal/board/stackchan_display.cc` 的 `ShowNotification()` 在已查版本是空實作；不能假設可直接使用。
- Motion 的 `setModifyLock()` 是布林旗標，不能當完整跨任務 Mutex；通知動作要有專屬資源仲裁與安全停止。
- 原廠 Xiaozhi Audio/TTS 所有權仍需實際確認，**未驗證前不啟用通知 TTS**。
- 不重新打造整個原廠 UI/Audio/Servo；優先沿用有證據支持的現有介面。

## 6. 最短開發順序（唯一 Checklist）

- [ ] **Phase 0｜先查證**：檢查 Git、使用者分支、Xiaozhi、LVGL、Servo、Audio；驗證 Codex 事件來源、Pi ARM64 部署與 eFuse/Bootloader；提交差異及風險報告。**不改程式、不燒錄。**
- [ ] **Phase 1｜電腦到 Pi**：Codex Bridge → Pi Coordinator → SQLite，含事件去重、重試、簡單登入／配對、Docker Compose；用測試證明能收事件。
- [ ] **Phase 2｜Pi 到 StackChan**：安全配對、接收通知、基本 Mew 畫面與可控 Servo；驗證 Xiaozhi 插話優先、斷線停用及重連。
- [ ] **Phase 3｜體驗改善**：Cursor（能驗證才上）、Mew 待機動畫、簡易 Dashboard、靜音設定與提示音。
- [ ] **Phase 4｜選做**：Xiaozhi 唯讀語音追問、ChatGPT/Grok、進階動畫與 CoreS3 SD 素材。

每一階段完成時必須提供：**改了哪些檔案、測試實際結果、未解決風險、下一步**。沒有通過測試不准勾完成。每次只做一個可驗收階段，進入下一階段需使用者確認。

## 7. 最低驗收條件

- Codex 真實事件成功傳至 Pi，斷網重送不產生重複通知。
- Pi 重啟後 SQLite 資料仍在；未授權裝置不能注入通知。
- StackChan 播放 Mew 基本完成提示，Xiaozhi 對話時不搶音訊／Servo。
- Pi 失聯、Token 失效、TTL 過期後不播放舊通知；通知取消後舊回呼不復活。
- 沒有確切成功證據時，絕不說「任務成功」。
- **eFuse 零新增寫入**，每次實機燒錄前有審查證據與使用者明確批准。

## 8. 直接交給 Codex 的第一段指令

> 請閱讀專案內 `docs/STACKCHAN_PERSONAL_SPEC.md`，它是唯一現行規格；舊 v0.1～v0.4 都只是歷史資料。**先執行 Phase 0 唯讀調查**，核對目前 Repo 與 M5Stack 上游、Xiaozhi/LVGL/Motion/Audio、Codex Hooks、Raspberry Pi ARM64，以及 ESP32-S3 eFuse/Bootloader 首次開機風險。請用繁體中文提供檔案路徑、證據、風險及 Phase 1 最小實作計畫。**現在禁止修改程式、燒錄、OTA、格式化、執行任何 eFuse 寫入。** 完成後停止，等待我批准。

## 官方參考來源

- 使用者 Repo：https://github.com/jason22432150/StackChan
- M5Stack 上游：https://github.com/m5stack/StackChan
- Raspberry Pi：https://www.raspberrypi.com/documentation/
- Docker Compose：https://docs.docker.com/compose/
- ESP32-S3 Secure Boot：https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/security/secure-boot-v2.html
- ESP32-S3 Flash Encryption：https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/security/flash-encryption.html
