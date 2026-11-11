# StackChan Firmware Windows 建置與燒錄指南

本專案需要 **ESP-IDF v6.1**（`>=6.1.0,<6.2.0`）。請勿使用 ESP-IDF 5.5。

以下路徑以本機（EIM 安裝）為例：

- 專案：`F:\project\StackChan\StackChan`
- ESP-IDF v6.1：`C:\esp\v6.1\esp-idf`
- 工具鏈：`C:\Espressif\tools`
- 啟動腳本：`C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1`

官方文件：[ESP-IDF v6.1](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/index.html)

---

## 0. 前置條件

- Windows 10 / 11
- 已用 [Espressif Installation Manager (EIM)](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/get-started/windows-setup.html) 安裝 ESP-IDF **v6.1**（target：`esp32s3`）
- 已安裝 `git`、`python3`
- StackChan 以 USB-C 接上電腦（需能傳資料的線）

---

## 1. 每個新 terminal 都要啟動 ESP-IDF 環境

Cursor / 一般 PowerShell **不會**自動載入 IDF。開新終端後先執行：

```powershell
. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1
idf.py --version
# 必須顯示：ESP-IDF v6.1.x
```

若出現 `idf.py: 無法將 'idf.py' 字詞辨識為...`，代表尚未 source 上面的 profile。

也可從開始功能表開啟 **ESP-IDF 6.1 PowerShell**，再 `cd` 到專案目錄。

---

## 2. 取得專案依賴（需要時）

```powershell
cd F:\project\StackChan\StackChan\firmware
python .\fetch_repos.py
```

---

## 3. Build

```powershell
cd F:\project\StackChan\StackChan\firmware

# 若先前用錯 IDF 版本建過，先清掉
Remove-Item -Recurse -Force .\build -ErrorAction SilentlyContinue

idf.py build
```

成功會看到：`Project build complete.`，並產生 `build\stack-chan.bin`。

---

## 4. Flash（燒錄到 StackChan）

1. USB 接上 StackChan
2. 在裝置管理員確認 COM 埠（例如 `COM8`）
3. 燒錄：

```powershell
# 自動偵測埠
idf.py flash

# 或指定埠（依你的裝置調整）
idf.py -p COM8 flash

# 燒錄後看 log
idf.py -p COM8 flash monitor
```

離開 monitor：`Ctrl+]`。

---

## 5.（可選）Host-side tests

不需板子：

```powershell
cd F:\project\StackChan\StackChan\firmware
cmake -S tests -B build-host-tests
cmake --build build-host-tests
ctest --test-dir build-host-tests --output-on-failure
```

---

## 常見陷阱

| 問題 | 解法 |
|------|------|
| `idf.py` 無法辨識 | 先 `. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1` |
| `idf (>=6.1.0,<6.2.0)` 解版失敗 | 必須用 ESP-IDF **v6.1**，不是 5.5 |
| `idf.py --version` 不是 6.1.x | 確認載入的是 v6.1 的 PowerShell profile |
| 找不到 COM 埠 | 換線／換 USB 口；裝置管理員確認 `COMx` |
| Flash 中途 `Lost connection` | 通常會自動重連；若失敗可再跑一次 `idf.py -p COMx flash` |

---

## 之後日常最短流程

```powershell
. C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1
cd F:\project\StackChan\StackChan\firmware
idf.py build
idf.py -p COM8 flash monitor
```
