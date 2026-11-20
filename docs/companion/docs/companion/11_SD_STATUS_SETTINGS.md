# 11｜StackChan microSD 儲存狀態頁設計（v2.3.1 新增）

## 1. 決策與範圍
- **新增到 StackChan 原廠設定 App**：`SETUP → Device → Storage / microSD`（若佈局需要亦可用獨立 `Storage` 區段）；不另建獨立 App。
- 顯示的是 **StackChan 本體 microSD 插槽**狀態，**不是 Raspberry Pi 4B 使用的第一張 128GB 卡**。
- 只提供 **唯讀狀態診斷**。不提供格式化、寫入測試、刪除、修復、分割、改檔案系統等按鈕。
- 不要求使用者插卡才可以使用 Companion；第二張 128GB 卡維持保留、不強迫投入使用。
- **CoreS3 官方標示 TF/microSD 最大支援 16GB**。現有兩張 128GB 卡不能視為已驗證可用；若無法掛載，顯示失敗狀態，不推斷卡片已損壞。
- 功能定位：v2.3.1 加入 MVP 的「設定頁診斷」項目，但**AI 對話／智能寵物／Agent 系統不得依賴 SD 掛載成功**。

## 2. UI 需求
導覽：`SETUP → Device → Storage / microSD`（與 Brightness、Volume、Timezone 同層）。

在成功掛載且能讀取檔案系統資訊時顯示：
- 狀態：`已掛載`。
- 總容量（GB）、已使用（GB）、剩餘（GB）；讀取的是實際檔案系統容量，不是宣稱的卡片包裝容量。
- 使用率進度條、使用百分比；數值須來自同一快照且全部做邊界檢查。
- 檔案系統類型（只有能可靠辨識時顯示，如 `FAT32`；否則 `未知`）。
- `重新檢查`、`返回` 按鈕。

在失敗狀態顯示：
- `未偵測到或無法讀取`：無卡片偵測硬體資訊時，**不得**把掛載失敗硬判為「未插卡」。
- `掛載失敗` / `檔案系統不支援` / `讀取容量失敗`：只有驅動可區分原因時才顯示精確錯誤；否則採通用訊息及簡短提示。
- 數字顯示 `—` 而不是 0 GB；避免將未知容量誤判為滿卡。

> UI 示意：`已掛載｜總容量 128.0 GB｜已使用 50.0 GB｜剩餘 78.0 GB｜39%`。這組數字為**示意**，不表示 128GB 卡實測相容。

## 3. 韌體整合點（已從分支確認）
- `firmware/main/apps/app_setup/app_setup.cpp` 的 `AppSetup::onOpen()` 內 `_menu_sections` 已有 `Device` 區塊，可加 `Storage / microSD` 項目，使用與其他選項相同的 Worker 生命週期。
- `firmware/main/apps/app_setup/workers/workers.h`：加入 `SdCardStatusWorker` 宣告。
- `firmware/main/apps/app_setup/workers/storage.cpp`（新增）：儲存狀態 UI、非阻塞重新整理、處理返回及 Worker 結束。
- `firmware/main/hal/hal_storage.cpp` 或 `firmware/main/hal/utils/storage/`（新增）：集中初始化／掛載檢查／容量查詢及資源釋放，不在 UI callback 直接碰 SPI 驅動。
- `firmware/main/hal/hal.h`：新增小型唯讀查詢介面，例如 `SdStatus querySdStatus()`；儲存狀態為 `absent_or_unreadable`, `mount_failed`, `mounted`, `read_error` 等，依實際可區分的能力決定。
- `firmware/main/CMakeLists.txt` 目前已有 `GLOB_RECURSE apps/*.cpp`、`hal/*.cpp`；新增檔案仍須驗證 ESP-IDF component deps 和完整建置。

## 4. 技術方案與注意事項
1. 先盤點 SPI bus 是否與 LCD／其他設備共用，確認腳位、初始化次序和現有 Board/HAL 的資源擁有者。官方 StackChan Arduino 範例使用 CS=4、SCK=36、MISO=35、MOSI=37；**這僅是硬體對照，不可直接把 Arduino `SD.begin()` 複製到目前 ESP-IDF 韌體**。
2. 優先採 ESP-IDF 6.1 的 SDSPI + FATFS / VFS 接口，或沿用專案實際已存在的對應驅動；`esp_vfs_fat_sdspi_mount()`、FatFs `f_getfree()` 等可作實作參考，依現有依賴與配置核對。
3. **禁止格式化**：掛載配置必須設定 `format_if_mount_failed=false`；不得呼叫任何 erase/format/repair API。只查詢 metadata，不做建立檔案測試。
4. SD 卡總／剩餘容量須以 64-bit 整數計算，避免 128GB 溢位；進位單位顯示 `GB`（10^9 bytes），內部保存 bytes，百分比在 `total>0` 時才計算。
5. SD 初始化、檢測與容量查詢可能阻塞，放在獨立工作任務或有界工作隊列；UI 更新仍走 LVGL lock/正確 UI thread；避免每幀輪詢。
6. 首次進入頁面及使用者點「重新檢查」時刷新即可；切出頁面停止進行中查詢／忽略過時結果。
7. SD bus 資源由一個 storage service 管理，不允許重複 mount、重複初始化共用 SPI、重複 unmount；若其他 App 已使用 SD，採共享狀態或安全拒絕，不強制奪取。
8. 插拔偵測能力需檢查硬體：若沒有 card detect 腳，僅在重新檢查時判斷狀態；不承諾熱插拔即時通知。
9. 只有明確讀取成功才顯示容量；異常值、溢位、未知格式都轉為保守錯誤狀態。
10. 不要求 Raspberry Pi 連線即可運作；也不使用 Pi 的容量資料假冒 StackChan SD 卡容量。

## 5. 驗收案例
| ID | 情境 | 預期結果 |
|---|---|---|
| SD-01 | 無卡，進入設定頁 | 迅速顯示 `未偵測到或無法讀取`，容量 `—`；不重啟、不卡住 |
| SD-02 | 已知相容的 FAT32 卡 | 成功時顯示總／已使用／剩餘與使用率；與 PC 查詢結果在單位換算誤差範圍內一致 |
| SD-03 | 128GB 卡（目前非官方保證） | 成功則顯示實際測得容量；失敗則顯示合理錯誤，**不得視為硬體故障證據** |
| SD-04 | 不支援格式／壞卡 | 失敗清楚、沒有任何自動格式化／寫入／修復 |
| SD-05 | 連續點重新檢查 | 忽略或合併重複請求，不崩潰、不重複初始化資源 |
| SD-06 | 切出設定頁／切換 Companion | UI 銷毀後無 use-after-free、無 LVGL 崩潰；原廠／Companion 可繼續使用 |
| SD-07 | Raspberry Pi 關閉 | StackChan 設定頁仍可獨立讀取 SD 狀態 |
| SD-08 | 進行 SD 檢查 | 不寫 eFuse、不擦 NVS、不修改 SD 內容或其他分割區 |

## 6. 明確非目標
- MVP 不支援 SD 檔案瀏覽、檔案管理、音訊／動畫直接從 microSD 串流。
- MVP 不支援 SD 卡格式化和自動修復。
- 不承諾 128GB 卡相容，容量相容性以官方規格與後續實機測試為準。

## 7. 官方資料與程式碼參考
- [你的設定 App 程式碼](https://github.com/jason22432150/StackChan/blob/my-stackchan-01/firmware/main/apps/app_setup/app_setup.cpp)
- [你的 Worker 介面](https://github.com/jason22432150/StackChan/blob/my-stackchan-01/firmware/main/apps/app_setup/workers/workers.h)
- [M5Stack CoreS3 產品規格：microSD 最大 16GB](https://docs.m5stack.com/en/core/CoreS3)
- [M5Stack StackChan SD Card 官方 Arduino 範例](https://docs.m5stack.com/en/arduino/m5cores3/sdcard)
- [Espressif ESP-IDF FAT Filesystem Support](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/api-reference/storage/fatfs.html)
- [Espressif ESP-IDF SD SPI Host Driver](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/api-reference/peripherals/sdspi_host.html)

## v2.3.3 與 AI 寵物的關係
此功能繼續留在原廠 `SETUP` 內而非獨立 Companion 頁面，**在 Pi 離線、App 未啟動或切換原廠 AI 之前都應可查**。Storage UI 僅報告 StackChan 本體 microSD 插槽的檔案系統狀態；不把 Pi 系統卡的容量資料混進來。卡片超過官方宣告的 16GB 支援容量時，失敗回報不可被解讀為必然損壞。
