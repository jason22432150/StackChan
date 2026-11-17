# 05｜安全、隱私、授權與 Fail-Closed

## 1. 安全模型

單一使用者但非無驗證；每個 Bridge、Coordinator、CoreS3、Dashboard 均有獨立身分與授權範圍。首次配對需人工確認；mDNS 僅發現服務不是身份信任證據。LAN 不等於可信；網路連線與政策驗證需雙重完成。任何憑證不得以明文記錄、匯出或 TTS 播報。

## 2. 權限分級

- Bridge：來源 Adapter 事件寫入、同步狀態查詢；無他機資料查閱權。
- CoreS3：接收本機 NotificationIntent、政策版本、回報本機 PresentationReceipt、按需查詢已授權短期歷史；不能遠端控制 Agent。
- Dashboard：身分驗證後查詢、搜尋、標記已讀、管理本系統設定；不提供修改 Agent Prompt、批准任務、取消執行、重試執行等操作。
- Coordinator 管理：裝置配對、密鑰撤銷、隱私政策與角色資產授權；高風險變更需核准。

## 3. 情境感知隱私

全域政策／敏感專案分類跨裝置同步；每台 StackChan 的手動隱私模式、當下情境、短期解鎖**獨立**。規則式時間／已授權設備／場域線索可輔助，但 Wi-Fi 連線不是私人環境的充分證據。手動模式優先於一般情境推論，但不能覆寫不可揭露的密鑰類安全底線。未知狀態 => 最小必要內容或禁止詳情，尤其 TTS。攝影機、聲紋及持續環境監聽不是預設要求。

`privacy_class` 建議：`public`、`internal`、`sensitive`、`secret`；最後類型永不作內容揭露。`sensitive` 在裝置、範圍、用途、期限均有效且環境允許時才可查閱；即使可信確認，也不代表公共空間可以朗讀。原始 Event payload 應白名單保留，路徑／Token／密碼等應遮蔽。

## 4. Fail-Closed 是不可變更安全底線

- Coordinator 身份無效／連線判定斷線／政策版本無法驗證／授權過期：**Agent 通知停用**，包含已顯示文字、通知音訊與 Notification Motion；Bridge 不得直連補救。
- 裝置可以保留原廠 Xiaozhi 與不含 Agent 事件的 Mew 待機，以及獨立的服務故障狀態圖示。
- 失聯偵測不可能物理上零延遲，必須設定 heartbeat／lease 上界，超時即停權。R-006 上界為 `kMvpSoftWorstCaseRevokeMs=4185`（心跳 4s＋P0-04 UI gap 185 ms）；CoreS3 實測樣本 `revoke_ms=4000` 落在預算內。短期解鎖不跨裝置、不在重連時自動繼承。
- 重新連線需檢查 Coordinator 身份→政策版本→撤銷狀態→穩定門檻→智慧補送；任何一步失敗維持 SUSPENDED／ERROR。
- 世代權杖在撤銷瞬間失效，非同步 UI、TTS、Servo 的提交點必須重新確認；已排隊的動畫不能在授權恢復前自行播放。

## 5. 備份與刪除

Bridge／Coordinator 短期資料保留的預設 7／14／30 天尚未最後決定；不將保存策略假裝已定。清除需要處理 Outbox 缺口、同步 watermark、刪除標記等必要對帳資訊，避免過期事件重匯入。CoreS3 只允許設定與經保護憑證持久化，不保存事件歷史。診斷匯出遮蔽憑證、路徑與敏感訊息；無龐大監控平台。

## 6. 威脅模型／必測案例

| 威脅 | 緩解及測試 |
|---|---|
| 未授權 Bridge 注入成功事件 | 憑證及來源身份檢查、schema、證據等級、拒絕冒名 |
| 異常 Policy Revocation 重連 | 撤銷版本校對、鎖定裝置範圍 |
| Coordinator 停用後舊 UI 回呼 | Generation 即刻失效、受控 UI 清除 |
| 惡意原始事件文字 | 大小限制、合法編碼、LVGL 安全渲染，不解讀命令 |
| 遠端傳入任意 Servo 座標 | 拒絕原始控制；只允許預審核動作 Profile 和物理限幅 |
| TTS 音訊洩漏 | 政策單獨過濾文字、音訊 lease、公共場域不朗讀敏感內容 |
| 設定檔被竄改 | 版本化、驗證簽章或完整性檢查設計（具體方案待 Phase 0） |
| 离線舊事件重入 | Cursor/epoch/TTL/刪除水位一致性測試 |
