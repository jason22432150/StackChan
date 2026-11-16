# 07｜測試策略、MVP 驗收與發行 Gate

## 1. 基本原則

自動化單元＋契約＋整合＋故障注入測試為常態，CoreS3 關鍵階段需人工實機驗收。使用者已選擇功能與穩定性驗收，不要求精密硬體實驗室；不代表可以用 Windows 模擬器取代實機。原廠 Xiaozhi 功能不受破壞是所有韌體版本的退件條件。

## 2. 測試矩陣

| ID | 測試 | 前置條件 | 通過條件／紀錄 |
|---|---|---|---|
| T-EVT-01 | 原生 Event ID 重複 | 同一事件多次送達 | 一筆邏輯事件；Outbox 可重試 |
| T-EVT-02 | UI 不確定信號 | 畫面停更新 | 僅 uncertain／inferred，不報成功 |
| T-EVT-03 | 可靠 response.completed | 回應結束 | 不推導 task.succeeded |
| T-EVT-04 | 後續矛盾證據 | success 推測後有 running 視覺證據 | 保留版本、更正／衝突標記 |
| T-SYNC-01 | Coordinator ACK 丟失 | Coordinator 已持久化 | Bridge 重送無重複匯入 |
| T-SYNC-02 | 序號缺口 | 101／103 成功、102 失敗 | ACK 只推進到 101 |
| T-SYNC-03 | Bridge epoch 重置 | DB 重建、sequence 從 1 起 | 舊新世代不碰撞 |
| T-SYNC-04 | 多 Bridge 時鐘偏差 | 相差數分鐘 | 不由時鐘武斷推任務因果 |
| T-PRES-01 | 各裝置獨立 | A 已播、B 排隊 | B 未被誤標記 Presented |
| T-PRES-02 | 重複 receipt | 同一 receipt 兩次 | 一次邏輯呈現更新 |
| T-PRES-03 | Dashboard 已讀 | B 仍未播放 | B 依政策仍可呈現 |
| T-PRES-04 | TTL 過期 | 恢復舊通知 | 不主動播，保留合法歷史 |
| T-SEC-01 | Coordinator 失聯 | 正在播放私密通知 | 停權、清屏、停通知 TTS／Servo，保留 Xiaozhi |
| T-SEC-02 | 政策撤銷 | 已授權敏感內容 | 立即停權，不繼承其它設備 |
| T-SEC-03 | 舊 Generation 回呼 | 取消後延遲 callback | 不產生新 UI/Audio/Motion 可見效果 |
| T-SEC-04 | 無權憑證 | 偽造 Bridge／Device | 拒絕 API／WebSocket，無事件注入 |
| T-SEC-05 | 敏感事件文字 | Token／私密路徑 | 螢幕/TTS/診斷依政策遮蔽 |
| T-XIAO-01 | Xiaozhi 搶占 | Agent TTS 播放中喚醒 | 原廠音訊正常，通知受控中斷 |
| T-XIAO-02 | 對話 40 分鐘 | 佇列大量事件 | 不讓裝置 RAM 無界增長，結束後智慧合併 |
| T-XIAO-03 | 提示音共存 | 原廠正在播音 | 不雙重啟用 Codec 或破壞輸出 |
| T-MOTION-01 | 取消 Servo | 正在移動時安全撤銷 | 無危險跳動、超限或卡死 |
| T-MOTION-02 | IMU 競爭 | 搖晃事件＋通知動作 | 原廠安全反應優先 |
| T-ASSET-01 | SD 拔除／壞檔 | Mew 外部素材運作中 | 內建角色備援，Xiaozhi 不崩潰 |
| T-ASSET-02 | 資源耗盡 | 高負載圖層／圖像 | 安全降級、無看門狗重啟 |
| T-PLAT-01 | Windows MVP | 真正 Codex/Cursor 事件、CoreS3 | 端到端通知／回執／離線恢復 |
| T-PLAT-02 | macOS/Linux 設計 | 可用 Bridge 實體／VM | 核心邏輯契約一致，功能分期驗收 |

## 3. 發行 Gate

- **G0 技術調查通過**：使用者分支／原廠對照、Xiaozhi 音訊獨占及 TTS 可行性、現有 LVGL／Motion、存儲與 CPU/PSRAM 量測的可驗證結論。
- **G1 契約凍結**：JSON Schema／OpenAPI、Event ID、資料庫 Migration、權限模型經契約測試與人類確認。
- **G2 核心資料同步**：事件去重、Outbox、ACK 缺口、Coordinator Fail-Closed 的自動化測試通過。
- **G3 實機第一通知**：CoreS3 訊息呈現、Xiaozhi 對話可用、斷線中斷、Receipt，人工實測通過。
- **G4 角色與語音**：Mew 全身、Motion、SD 降級、通知音訊安全；語音追問若原廠介面不可行須標記限制並向使用者回報，不可偽造完成。
- **G5 完整發行**：多裝置、跨平台、隱私授權、長時間穩定、檔案／版本／備份與診斷；主分支 merge 和 OTA／燒錄需明確核准。

## 4. 指標定義（測試後填值，禁止猜測）

- 失聯判定上界（ms）／實際通知清除時間（ms）；Xiaozhi Audio 中斷／搶占失敗次數。
- UI 鎖等待／持鎖時間；stackchan update task 調度週期；PSRAM 峰值；每種角色圖片載入時間。
- 同步 ACK 正確率、重試數、重複事件數；大量佇列下最長延後時間與 backlog 高水位。
- Servo 角度邊界、速度／碰撞／失力回復；持續運行時長及掉線次數。

測試證據必須附真實原始碼 commit、firmware build ID、CoreS3 型號、環境、觀測結果與人類驗收，不將「測試清單已寫完」當作已測試。
