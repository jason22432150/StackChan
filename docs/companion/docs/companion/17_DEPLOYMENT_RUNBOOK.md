# 17｜部署、更新、故障回退與命令說明（v2.3.3）

> 內容是**未實作的部署計畫與示例命令**，不是要求現在執行。先確認 `coordinator/` 實際路徑、Python 套件及 systemd 檔案存在後才可操作。以下每個命令都附原因與效果。

## 1. 硬體和系統
- Raspberry Pi 4B，使用第一張 128GB microSD 安裝 Raspberry Pi OS（建議 64-bit）。主要執行 Python Coordinator、SQLite、雲端 API Client、輕量 STT/TTS client，不在 Pi 4B 本地跑大型 LLM。
- StackChan CoreS3 新增 Mooncake Companion App；保留原廠 Xiaozhi、Launcher、App Setup、音訊/伺服馬達驅動。
- 第二張 128GB microSD 保留；StackChan 不依賴該卡啟動、存記憶或播動畫。

## 2. 開發機：檢查與建立分支（只在確認基線及工作樹後操作）
| 命令 | 原因與結果 |
|---|---|
| `git status` | 查看目前修改及分支，只讀，不更改任何檔案。若有未提交變更，先保護它們。 |
| `git switch my-stackchan-01` | 切回確認的基礎分支；會改變工作區檔案版本，有未提交衝突時不能強行執行。 |
| `git switch -c feature/stackchan-companion` | 從當前分支建立新開發分支並切換，避免直接修改基礎分支。 |
| `idf.py --version` | 檢查 ESP-IDF 版本是否符合 Repository 開發說明的 v6.1 系列，只讀。 |
| `cd firmware && idf.py build` | 編譯 ESP32-S3 韌體，輸出建置結果；**不會燒錄晶片、不寫 eFuse**。 |

**禁止自動執行**：`idf.py flash`、`espefuse.py burn_*`、Secure Boot/Flash Encryption provisioning 等。任何刷機要先確認 Port、分割表及回退映像，取得使用者明確同意；eFuse 寫入在本專案一律禁止。

## 3. Raspberry Pi：Python 虛擬環境與測試（示意）
假設檔案存在 `~/StackChan/coordinator/`，且已完成 `pyproject.toml` / requirements：

| 命令 | 為什麼執行、效果 |
|---|---|
| `cd ~/StackChan/coordinator` | 進入 Pi Coordinator 專案，後續安裝與測試只在此執行。 |
| `python3 -m venv .venv` | 建立隔離的 Python 環境；不直接改作業系統的 Python 套件。 |
| `. .venv/bin/activate` | 啟用該環境，之後 `python`/`pip` 優先使用 `.venv` 內版本。 |
| `python -m pip install -e '.[dev]'` | **僅限專案已宣告 dev extras 時**安裝 Coordinator 相依套件；會下載並安裝 Python 套件，需檢查清單與網路。 |
| `python -m pytest` | 執行模擬／單元測試，不應呼叫真實雲端或操控硬體，除非明確切換 integration profile。 |
| `python -m companion.main` | **僅當實際套件入口存在**時在前景啟動 Pi 服務，觀察連線與錯誤；Ctrl+C 中止。 |

## 4. 開機自動啟動（systemd）
- 將 `stackchan-companion.service` 的 `WorkingDirectory`、執行 Python、使用者與 EnvironmentFile 改成真實 Pi 路徑；不可把 API Key 寫入 service 原始碼或 Git。
- 安裝 service 單元後先用 `sudo systemctl daemon-reload`（重新讀取服務配置），再用 `sudo systemctl enable --now stackchan-companion`（設定開機啟動並立刻啟動）。這兩步會改動 Pi 的服務設定，不影響 ESP eFuse。
- `systemctl status stackchan-companion`：查看執行狀態；`journalctl -u stackchan-companion -n 100 --no-pager`：查看近 100 行記錄，不應含金鑰/音訊全文。
- `sudo systemctl restart stackchan-companion`：部署更新後重新啟動 Pi 服務，**會中斷當下對話**，StackChan 應轉離線待機並重連。

## 5. 更新和回退
- AI Provider、Prompt、興趣、主動互動規則等修改只更新 Pi Python 程式，先備份 `data/companion.db` 與 `config.yaml`（私密 API Key 另行保護），再部署新版本。
- 更新後執行 pytest、啟動健康檢查、Pi↔StackChan 重連測試；故障時切回前一個可用的 Pi 程式版本與相容 DB 備份。
- StackChan 韌體更動需額外完整編譯與裝置驗證；不用為每個個性參數改動重新刷機。
- 無 Pi 時 Companion 只執行基礎離線動畫，不能假裝雲端成功；原廠功能保持可進入。

## 6. 常見問題快速排除
| 現象 | 先查什麼 | 避免做什麼 |
|---|---|---|
| 裝置顯示 OFFLINE | Pi 電源／網路、service status、IP 配置 | 不要直接重刷韌體 |
| 語音沒聲音 | Audio Codec owner、TTS 播放 state、音量 | 不要在多個模組同時開喇叭 |
| 喚醒詞失靈 | 誤觸/漏觸統計、喚醒策略位置、麥克風狀態 | 不要一開始強推全雙工 |
| 寵物太吵 | `focus_mode`、quiet hours、proactive quota | 不要只靠改 Prompt 避免騷擾 |
| SD 顯示無法讀取 | 是否插卡、格式、官方容量限制、共用 SPI | **不要自動格式化** |
| 原廠 AI 切換失敗 | Mooncake/Xiaozhi 生命週期、warm reboot | 不刪原廠入口 |

## 官方來源
- Raspberry Pi：https://www.raspberrypi.com/documentation/
- Python venv：https://docs.python.org/3/library/venv.html
- systemd：https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html
- ESP-IDF：https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/
