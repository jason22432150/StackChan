# 06｜Mew 全身角色、SD 素材與動畫時間軸

## 1. 設計目標

Mew 不是只有臉：需要完整身體、表情、眼睛／眨眼、嘴巴、姿態及與 Servo／聲音協調。原廠 Avatar 必須可回退，不修改原廠 Xiaozhi 核心語音邏輯。可替不同 Agent 指定角色、動作模板與通知規則，保留原始事件語義。

## 2. 層次

`CharacterProfile`（角色 identity、皮膚）→ `StateGraph`（idle/listening/thinking/happy/concerned 等）→ `AnimationTimeline`（繪圖、圖層、帧時間、Servo 事件、音效觸發）→ `Renderer`（LVGL 安全更新）＋`MotionAdapter`＋`AudioAdapter`。

AnimationTimeline **必須聲明式且經驗證**，不允許角色素材執行不受限的腳本。素材預載、解析、裁切與轉換在電腦端，CoreS3 僅允許界限內解碼。資產內容不得持有事件隱私授權；文字顯示仍由 NotificationIntent 控制。

## 3. 資產部署

- 優先 SD 卡的角色圖片、動畫配置與索引，Flash／韌體提供最小原廠保底角色。
- SD 可手動更新或由授權 Bridge／Coordinator LAN 上傳；上傳前驗證大小、格式、checksum、路徑與版本；不得覆寫韌體私密配置。
- 不建立統一插件套件格式或公共社群市集；動畫模板、角色資產、規則配置各自版本與 schema。
- 資產下載／驗證／替換不能於 Audio 或 LVGL 高優先執行緒進行；採分段、限速和安全切換。
- 素材損毀／SD 拔除：停用該素材，退回內建角色；**不自動回滾韌體或整套 SD 到舊版**。

## 4. 建議動畫 Profile

| 狀態 | 全身畫面 | Motion | Audio | 備註 |
|---|---|---|---|---|
| idle | 輕微浮動／眨眼 | 非侵入式小動作 | 靜音 | CPU 高負載可降階 |
| agent.response.completed | 中性點頭／提示卡 | 可選 | 短音（經驗證） | 不宣稱任務成功 |
| agent.task.succeeded | 開心全身動作 | 安全範圍動作 | 可選 TTS | 僅當真有成功證據 |
| agent.task.failed | 關切動作 | 減弱 | 可選 | 不朗讀私密詳情 |
| agent.awaiting_user | 等待姿勢 | 適度提醒 | 可選 | TTL 與新狀態重驗 |
| xiaozhi.listening | 原廠對話優先 | 原廠優先 | 禁止通知播報 | 撤銷通知 lease |
| coordinator.suspended | 一般待機＋狀態圖示 | 待機安全 | 禁止 Agent 音效 | 所有 Agent 文字清除 |

## 5. 視覺編輯器與模擬器

建議 PC Web 時間軸編輯器、JSON/YAML 匯入匯出與 Windows LVGL 模擬器。模擬器驗證表情、圖層、碰撞與時序不等於硬體資源和 Servo 安全驗證；實機 Preview 須經核准。第一版角色素材需從單一全身 Mew + 原廠備援開始，確認成本再擴充其他角色。

## 6. 實機資源預算

PSRAM、Flash、圖片快取、SD I/O、每秒更新率及 Servo 動作上限尚無可保證數值；Phase 0 必須量測 `heap_free`、PSRAM 高水位、幀更新延遲、Xiaozhi 音訊中斷次數、SD 載入耗時。採動態降級：關閉非必要圖層、減少表情頻率、停用音效或外部 SD 素材，最終內建角色待機。
