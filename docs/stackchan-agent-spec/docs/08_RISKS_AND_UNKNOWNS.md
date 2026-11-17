# 08｜技術風險登錄與未決事項

## 1. 風險分級

P0＝若未驗證不得進入韌體實作；P1＝MVP Gate；P2＝擴充階段。狀態 `UPSTREAM-VERIFIED` 只指上游原始碼事實，不代表本地分支及硬體通過。

| ID | 優先級 | 風險／不確定性 | 目前證據 | 必須完成的 Gate |
|---|---|---|---|---|
| R-001 | P0 | 使用者分支原始碼無法取得／與上游不同 | 上游可讀、個人庫未取到 | 核對個人分支 commit／diff／實際依賴 |
| R-002 | P0 | Xiaozhi Audio/TTS 播報入口不明 | `Application::PlaySound` 有已知音效入口 | 調查音訊依賴／Session Ownership／TTS 接法；不得直接 Codec 注入 |
| R-003 | P0 | Xiaozhi `is_idle` 不是 Audio lease | `SetStatus` 設定 idle flag | 明確事件／資源仲裁證據及實機交接 |
| R-004 | P0 | LVGL 更新任務持鎖延遲 | 上游 `_stackchan_update_task` 鎖內非 idle 延遲 | 量測 UI Lock、通知清除上界、避免死鎖 |
| R-005 | P0 | Servo `ModifyLock` 只是 bool | `Motion::setModifyLock()` 實作 | ResourceArbiter＋Servo 安全限制／IMU 衝突測試 |
| R-006 | P0 | Fail-Closed 失聯判定上界未設定 | 軟路徑預算已設計：`kMvpSoftWorstCaseRevokeMs=4185`（heartbeat 4000＋P0-04 UI gap 185）；host CTest／pytest 對齊；**實機未量測** | 燒錄後實測最壞撤銷時間，方可關閉本風險 |
| R-007 | P0 | Agent 原生 Hook／Cursor 事件能力差異 | 尚未逐版本驗證 | 官方介面／實測樣本／可信等級矩陣 |
| R-008 | P1 | CoreS3 `ShowNotification()` 空實作 | 上游已讀到空函式 | 受控 Presenter＋ACK／清屏測試 |
| R-009 | P1 | SD／PSRAM 限額與大量 Mew 動畫 | 部分上游圖片快取邏輯 | 素材負載基準、壞檔降級測試 |
| R-010 | P1 | SQLite 跨 Bridge 對帳與清理重播 | 純契約提案 | 故障注入、缺口重傳、清理水位測試 |
| R-011 | P1 | 多裝置短期授權與撤銷傳播 | 已確認架構，未實測 | 授權範圍、撤銷競態測試 |
| R-012 | P1 | Windows/macOS/Linux 監聽 UI 行為不一 | Adapter 類型規劃 | 平台功能矩陣；不將未知來源當 verified |
| R-013 | P2 | 遠端中繼與 NAS 部署 | 尚未設計供應商依賴 | 端到端憑證／網路安全驗證 |
| R-014 | P2 | 情境感知感測器的誤判 | 已選規則式手動優先 | 不依賴攝影／聲紋；失敗採保守預設 |
| R-015 | P2 | Windows LVGL 模擬器與 CoreS3 差異 | 有使用者先前成功模擬器經驗，但不可當實機證據 | 共同契約＋CoreS3 驗收 |

## 2. 尚未定量的參數

事件歷史保存天數、不同事件 TTL、心跳與延遲上界、Coordinator 穩定性門檻、重試 jitter、CoreS3 Queue 容量、記憶體/CPU 畫面負載、Servo 運動限制、音訊仲裁優先級細節，都須由 Phase 0 可驗證結果和使用者驗收定案。嚴禁在正式測試報告中填寫臆測的 FPS、秒數、負載百分比或宣稱所有 Agent Hooks 均已支援。

## 3. 版本與替代方案授權

技術替代路徑應記錄：現有方案→為何不可行→候選方案→風險→成本→對原廠相容性的影響→是否須人工核准。低風險孤立測試可在**已授權實作階段**自行進行；修改原廠安全／Xiaozhi、Merge 主分支、燒錄、修改密鑰及刪除使用者資料必須先取得明確許可。
