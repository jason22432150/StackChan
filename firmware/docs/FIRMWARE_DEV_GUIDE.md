# StackChan 韌體修改入門指南

這份韌體是 **ESP-IDF（ESP32-S3）+ Mooncake App 框架**，不是單純的 Arduino sketch。建議先搞懂「改哪一層、怎麼驗證」，再動手。

Windows 建置與燒錄細節見 [WIN_SETUP.md](./WIN_SETUP.md)。

---

## 1. 先確認你能建置

Windows 日常最短流程：

```powershell
. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1
cd F:\project\StackChan\StackChan\firmware
idf.py --version   # 必須是 ESP-IDF v6.1.x
idf.py build
idf.py -p COM8 flash monitor
```

能 `build` + `flash` + 看到 serial log，才算進入可改韌體的狀態。

官方文件：[ESP-IDF v6.1](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/index.html)

---

## 2. 專案地圖（改什麼就找哪）

| 目錄 | 角色 | 適合先改？ |
|------|------|------------|
| `firmware/main/main.cpp` | 開機入口：初始化 HAL、安裝 Apps、主迴圈 | 了解流程用 |
| `firmware/main/apps/` | 各個 App（Launcher、Avatar、Dance、Setup…） | **最推薦入口** |
| `firmware/main/hal/` | 硬體抽象：螢幕、馬達、音訊、Wi-Fi、BLE… | 改硬體行為時 |
| `firmware/main/stackchan/` | 角色表現：臉、表情、動畫、motion、LED | 改外觀／動作時 |
| `firmware/xiaozhi-esp32/` | AI Agent 底層（語音／協定） | 後期再碰 |
| `firmware/main/Kconfig.projbuild` | menuconfig 選項 | 開關功能用 |

### 啟動流程

```
app_main()
  → GetHAL().init()
  → 安裝 Mooncake Apps（Launcher / Avatar / …）
  → while 迴圈：GetMooncake().update()
  → 需要時進入 Xiaozhi AI Agent
```

對應程式在 `firmware/main/main.cpp`：

```cpp
extern "C" void app_main(void)
{
    // Setup logger
    // HAL init
    GetHAL().init();

    // Install apps: AppLauncher, AppAiAgent, AppAvatar, ...
    while (1) {
        GetMooncake().update();
        if (GetHAL().isXiaozhiStartRequested()) {
            break;
        }
    }

    // Start xiaozhi, never returns
    GetHAL().startXiaozhi();
}
```

---

## 3. 建議的第一個修改：從 AppTemplate 學生命週期

官方範本：`firmware/main/apps/app_template/`。

### Mooncake App 生命週期

1. `onCreate` — 安裝時
2. `onOpen` — 開啟時（建 UI）
3. `onRunning` — 執行中（每幀／每圈）
4. `onClose` — 關閉時（釋放資源）

### 注意事項

- 操作 LVGL UI 時用 `LvglLockGuard`（或 `GetHAL().lvglLock()` / `GetHAL().lvglUnlock()`）
- 硬體／時間請走 `GetHAL()`，不要到處直接碰 driver

### 若要真正掛上這個 App

1. 在 `apps/apps.h` 加入 `#include`
2. 在 `main.cpp` 的 `installApp(...)` 註冊

（目前 template 多半是教學用，預設未必已安裝。）

---

## 4. 依目標選「改哪裡」

| 你想做的事 | 從這裡開始 |
|------------|------------|
| 加一個自己的畫面／選單項目 | `apps/`（複製 `app_template` 或改 `app_launcher`） |
| 改開機行為、功能開關 | `app_setup/`、`hal_toggles`、`Kconfig.projbuild` |
| 改表情、眨眼、說話泡泡 | `stackchan/avatar/` |
| 改轉頭、跳舞、待機動作 | `stackchan/motion/`、`apps/app_dance/` |
| 改 LED / Neon | `stackchan/addons/neon_light/` |
| 改馬達、觸控、IMU、螢幕細節 | `hal/`（例如 `hal_servo.cpp`、`hal_head_touch.cpp`） |
| 改 AI 語音對話 | `xiaozhi-esp32/` + `app_ai_agent`（較深） |

原則：**先改 App 層，再下探 HAL / stackchan**。少直接改 `xiaozhi-esp32`，除非你明確要動 AI pipeline。

---

## 5. 實際開發節奏

1. 想清楚要改的是「畫面／動作／硬體／AI」哪一類
2. 找到對應目錄，先讀既有 App（例如 `app_dance` 或 `app_launcher`）
3. 小改 → `idf.py build` → `flash monitor` → 看 log
4. 不需板子也可先跑 host tests（motion 相關）：

```powershell
cd F:\project\StackChan\StackChan\firmware
cmake -S tests -B build-host-tests
cmake --build build-host-tests
ctest --test-dir build-host-tests --output-on-failure
```

---

## 6. 建議練習路徑

依難度由淺到深：

1. **加一個新 App**（從 `app_template` 掛到 Launcher）
2. **改表情／頭的動作**（`stackchan/avatar/`、`stackchan/motion/`）
3. **改 Setup 選單或開機行為**（`app_setup/`、`hal_toggles`）
4. **再進 HAL / Xiaozhi**（硬體細節與 AI pipeline）

---

## 相關文件

- [WIN_SETUP.md](./WIN_SETUP.md) — Windows 建置與燒錄
- [README.md](./README.md) — Build / Flash 摘要
- [ESP-IDF v6.1 Programming Guide](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/index.html)
