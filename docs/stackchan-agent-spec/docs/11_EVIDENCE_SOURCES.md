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
