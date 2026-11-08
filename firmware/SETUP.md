# StackChan Firmware 建置與燒錄指南

本專案需要 **ESP-IDF v6.1**（`>=6.1.0,<6.2.0`）。請勿使用 ESP-IDF 5.5。

以下路徑以本機為例：

- 專案：`~/project/stack-chan/StackChan`
- ESP-IDF v6.1：`~/esp/esp-idf-v6.1`

---

## 0. 前置條件

- macOS（Apple Silicon）
- 已安裝 `git`、`python3`、`cmake`、`ninja`

---

## 1. 安裝 ESP-IDF v6.1（只需一次）

**務必開新的乾淨 terminal**，不要先 `source` 舊的 ESP-IDF 5.5。

```bash
mkdir -p ~/esp
cd ~/esp

# 若尚未 clone
git clone -b v6.1 --recursive https://github.com/espressif/esp-idf.git esp-idf-v6.1

cd ~/esp/esp-idf-v6.1

# 若 shell 曾載入過 5.5，先清掉再裝
unset IDF_PATH IDF_PYTHON_ENV_PATH IDF_TOOLS_PATH ESP_IDF_VERSION OPENOCD_SCRIPTS

./install.sh esp32s3
```

成功後會有：

- `~/.espressif/python_env/idf6.1_py3.15_env`
- `~/.espressif/espidf.constraints.v6.1.txt`

官方文件：[ESP-IDF v6.1](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/index.html)

---

## 2. 每個新 terminal 都要啟動環境

```bash
. ~/esp/esp-idf-v6.1/export.sh
idf.py --version
# 必須顯示：ESP-IDF v6.1.x
```

若仍顯示 `v5.5.4`，代表載入了舊環境；開新 terminal 再跑上面這行。

---

## 3. 取得專案依賴（需要時）

```bash
cd ~/project/stack-chan/StackChan/firmware
python3 ./fetch_repos.py
```

---

## 4. Build

```bash
cd ~/project/stack-chan/StackChan/firmware

# 若先前用錯 IDF 版本建過，先清掉
rm -rf build

idf.py build
```

成功會看到：`Project build complete.`，並產生 `build/stack-chan.bin`。

---

## 5. Flash（燒錄到板子）

接上 USB 後：

```bash
# 自動偵測埠
idf.py flash

# 或指定埠（依你的裝置調整）
idf.py -p /dev/cu.usbmodem* flash

# 燒錄後看 log
idf.py -p /dev/cu.usbmodem* flash monitor
```

離開 monitor：`Ctrl+]`。

---

## 6.（可選）Host-side tests

不需板子：

```bash
cd ~/project/stack-chan/StackChan/firmware
cmake -S tests -B build-host-tests
cmake --build build-host-tests
ctest --test-dir build-host-tests --output-on-failure
```

---

## 常見陷阱

| 問題 | 解法 |
|------|------|
| `idf (>=6.1.0,<6.2.0)` 解版失敗 | 必須用 ESP-IDF **v6.1**，不是 5.5 |
| `Python environment ... generated for ESP-IDF 5.5` | 在**乾淨 shell** 跑 `install.sh`，或先 `unset IDF_PYTHON_ENV_PATH` |
| `espidf.constraints.v6.1.txt doesn't exist` | 尚未成功跑完 `./install.sh` |
| `idf.py --version` 仍是 5.5.4 | 開新 terminal，只 source `~/esp/esp-idf-v6.1/export.sh` |

---

## 之後日常最短流程

```bash
. ~/esp/esp-idf-v6.1/export.sh
cd ~/project/stack-chan/StackChan/firmware
idf.py build
idf.py flash monitor
```
