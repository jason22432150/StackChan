# 09｜原始碼證據、官方資料與待驗證項目

## GitHub 基礎
- Repository：https://github.com/jason22432150/StackChan
- Base branch：https://github.com/jason22432150/StackChan/tree/my-stackchan-01
- 本次已確認 commit：`4a39d5114c5d8ea555444396434918db6a0f5656`；開始開發前需再次查核 HEAD。

| 已由原始碼確認的現況 | 位置 |
|---|---|
| 原廠 Mooncake ↔ Xiaozhi 切換流程 | `firmware/main/main.cpp` |
| 原廠 AI App 呼叫 `requestXiaozhiStart` | `firmware/main/apps/app_ai_agent/app_ai_agent.cpp` |
| Mooncake App 範本及 LVGL 鎖 | `firmware/main/apps/app_template/app_template.cpp` |
| 音訊 Codec 的錄音/播放基礎 | `firmware/main/hal/audio.cpp` |
| 原廠 Avatar WebSocket、Opus、TextMessage、Motion 類型 | `firmware/main/hal/hal_ws_avatar.cpp` |
| 隨機低頻待機馬達邏輯 | `firmware/main/stackchan/modifiers/idle_motion.h` |
| CMake 遞迴納入 apps/*.cpp | `firmware/main/CMakeLists.txt` |
| Assets 分割區的圖像載入 | `firmware/main/assets/assets.cpp` |
| ESP-IDF / Mooncake 韌體開發指南 | `firmware/docs/FIRMWARE_DEV_GUIDE.md` |

## 官方與技術文件
- M5Stack StackChan：https://docs.m5stack.com/en/StackChan
- M5Stack CoreS3：https://docs.m5stack.com/en/core/CoreS3
- Espressif ESP-IDF v6.1：https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/index.html
- Raspberry Pi 官方文件：https://www.raspberrypi.com/documentation/
- Raspberry Pi OS：https://www.raspberrypi.com/software/
- Xiaozhi ESP32：https://github.com/78/xiaozhi-esp32
- FastAPI：https://fastapi.tiangolo.com/
- Python asyncio：https://docs.python.org/3/library/asyncio.html
- SQLite：https://www.sqlite.org/docs.html
- OpenAI API pricing：https://openai.com/api/pricing/
- Gemini API docs：https://ai.google.dev/gemini-api/docs

## 尚待開發或實機驗證
1. 是否能從 Companion 直接利用目前 Codec 進行非原廠 AI 的長時間穩定收音、輸出與釋放。
2. 「雙喚醒」應選 ESP32 端喚醒詞或 Pi 端的輕量偵測；支援中文自訂喚醒詞的模型及可接受誤觸發率。
3. PCM/Opus 音訊時序、jitter buffer、喇叭播放中聲音反饋／自我喚醒問題。
4. 新 Companion 自動啟動如何與原有 `startAiAgentOnBoot` 設定安全相容。
5. 原廠 Xiaozhi 結束後能否不重啟返回 Launcher；不應假設可直接互切。
6. 本機中文字型／字幕、動畫素材、ESP32-S3 PSRAM/Flash 預算。
7. 兩個真實雲端 LLM provider 的金鑰、定價、可用模型、繁體中文品質；STT/TTS 可用語言及流式限制。
8. Ai 自主規則和 API 額度限制是否維持使用者想要的自由度與低延遲。
9. Pi 4B 實際 RAM 容量、OS 和電源狀態；音訊/喚醒引擎與 Python 同時運作之穩定性。
10. Agent Bridge 各應用能提供哪些確定事件，不能假設全部有官方 hook。
11. StackChan 的 128GB microSD 未被驗證相容，因此不列為依賴。

## 狀態
本文件描述**目標方案**與已讀取的程式碼證據；尚未建立開發分支、修改 Repo、燒錄或做實機測試。

## v2.3.1 新增官方依據與未驗證事項
- **原始碼已確認**：`firmware/main/apps/app_setup/app_setup.cpp` 的 `Device` 區塊與 `workers.h` 的 Worker 架構適合新增 Storage 頁。
- **官方確認**：M5Stack CoreS3 文件標示 `TF Card Maximum Supported Capacity: 16GB`；StackChan 官方 Arduino SD 範例提供 FAT32 和 SPI 腳位參考，但不是本案 ESP-IDF 6.1 已完成的驅動。
- **尚未驗證**：你的 128GB 卡是否能被 ESP-IDF 原廠韌體識別、SD 是否與其他外設共用 SPI、Card Detect/熱插拔支援、讀取容量是否穩定。
- 官方資料：https://docs.m5stack.com/en/core/CoreS3 、 https://docs.m5stack.com/en/arduino/m5cores3/sdcard 、 https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/api-reference/storage/fatfs.html 。

## v2.3.3 新增依據／變更
- 開發基線：`my-stackchan-01`，已核對 SHA `4a39d5114c5d8ea555444396434918db6a0f5656`（核對日期 2026-11-20）。實際開發前仍需核對 HEAD 是否更動。
- `firmware/main/main.cpp`：Mooncake App 安裝與 Xiaozhi 接管入口已核對。
- `firmware/main/apps/app_setup/app_setup.cpp`：Settings 的 Device 區塊與 Worker 生命週期已核對。
- `firmware/main/hal/audio.cpp`：`InputData` / `OutputData` 錄放音測試可見，尚**不能**證明 Companion 雙向音訊串流已可直接使用。
- `firmware/main/hal/hal_ws_avatar.cpp`：既有 Opus、TextMessage、ControlMotion 封包類型可見；新的 Companion 協定是草案，需另行實作／版本協調。
- `firmware/main/assets/assets.cpp`：資源從 Assets 分割區取出，不能假設原廠現有動畫從 microSD 讀取。
- M5Stack CoreS3 官方列出 TF/microSD 最大支援 16GB；第二張 128GB 卡不是已驗證相容。
- **「自然寵物型」與「五類興趣」是使用者已確認的新設計需求，並非原廠實作。**頻率與成長公式都是第一版建議，應在真機調整。

## 官方連結（2026-11-20 核對）
- M5Stack CoreS3：https://docs.m5stack.com/en/core/CoreS3
- M5Stack CoreS3 microSD 範例：https://docs.m5stack.com/en/arduino/m5cores3/sdcard
- ESP-IDF FATFS：https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/api-reference/storage/fatfs.html
- ESP-IDF SDMMC：https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/api-reference/storage/sdmmc.html
- Raspberry Pi 官方：https://www.raspberrypi.com/documentation/
- SQLite 官方：https://www.sqlite.org/docs.html
- OpenAI API 價格（僅供費用評估）：https://platform.openai.com/pricing/
