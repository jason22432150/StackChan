# AppCompanion（Phase 0）

Mooncake 獨立 App 空殼：

- Launcher 可開啟／以 home indicator 退出
- `onClose` 釋放 LVGL UI
- **不**請求 Xiaozhi、**不**占用 Audio Codec、**不**連 Pi、**不**控制馬達
- **不**呼叫 `requestWarmReboot`（與 Avatar/Dance 不同；Phase 0 未取得需 reboot 才能釋放的資源）

## 生命週期清理設計（P0-04）

| 資源 | onOpen | onClose |
|---|---|---|
| LVGL 根畫面／標籤 | 建立 | `reset()` |
| home indicator / status bar | 建立 | `destroy_*` |
| 麥克風／喇叭 | 未取得 | N/A（後續 Phase 必須先停播再釋放） |
| WebSocket | 未連線 | N/A（後續 Phase 必須關閉） |
| 馬達 | 未控制 | N/A |

後續 Phase 接入音訊／WS 時，必須保持「關閉 Companion 後原廠 Xiaozhi 可依既有流程使用硬體」的約束。
