# R-006 CoreS3 失聯撤銷實機量測

- 時間（UTC）：2026-11-17T03:04:40Z
- 裝置：ESP32-S3 rev v0.2（M5Stack StackChan / CoreS3 路徑），USB `/dev/cu.usbmodem1401`，MAC `80:45:6b:56:07:90`
- 韌體：`CONFIG_STACKCHAN_R006_REVOKE_PROBE=y` 診斷建置；`FailClosedRevokeProbe` 以 20 ms 節奏 poll（獨立 task，Hal::init 後啟動）
- 軟體預算：`kMvpSoftWorstCaseRevokeMs=4185`（heartbeat 4000＋P0-04 UI gap 185）
- 序列金樣：

```
# captured_at_utc=2026-11-17T03:04:12Z
[1794884651358] [[32minfo[0m] [HAL] R006_MEASURE revoke_ms=4000 budget_ms=4185 interrupted=true within_budget=true
```

- 結果：`revoke_ms=4000` ≤ `budget_ms=4185`，`interrupted=true`，`within_budget=true`
- 說明：本樣本為 20 ms 專用 probe 節奏下的壁鐘；軟體最壞上界仍保留 4185 ms 以涵蓋 P0-04 最大 UI 更新間隔。未改 Xiaozhi Audio／Servo 路徑。
- 診斷開關預設 `n`；量測後應關閉 `CONFIG_STACKCHAN_R006_REVOKE_PROBE`。
