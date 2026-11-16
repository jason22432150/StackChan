# 12｜CI／PR 契約測試規範（P1-07）

## 1. 唯一任務清單

- **唯一正式開發清單**：`docs/09_DEVELOPMENT_CHECKLIST.md`
- 其他規格文件可含驗收矩陣／風險表，但**不得**另建平行 task list。
- PR 描述應標明對應 checklist 編號（例如 `P1-07`），並在合併前更新 Evidence。

## 2. 契約測試（PR 必跑）

Workflow：`.github/workflows/agent-contracts.yml`

必跑範圍（host 端，不含韌體燒錄）：

| 目錄 | 目的 |
|---|---|
| `tests/contracts` | JSON Schema／OpenAPI 授權閘道 |
| `tests/bridge` | Bridge SQLite Outbox |
| `tests/coordinator` | Coordinator SQLite／migration |
| `tests/security` | 配對／政策／密鑰保護 |
| `tests/retention` | 保留清理／禁止重導入 |
| `tests/meta` | 清單唯一性與 CI 規範自檢 |

本機對齊指令：

```bash
uv sync --group dev
uv run pytest tests/contracts tests/bridge tests/coordinator tests/security tests/retention tests/meta -q
```

CI **通過 ≠** CoreS3 實機／Xiaozhi 音訊驗收通過。

## 3. 高風險合併需人工授權

下列變更**不得**僅因 CI 綠燈自動合併，必須明確人類批准：

1. 修改／合併至 `main`／`master`
2. 修改 `firmware/`、`firmware/xiaozhi-esp32`、`firmware/patches/`
3. 燒錄 CoreS3、OTA、變更原廠 Xiaozhi 設定／NVS
4. 對外綁定非 loopback（非 `127.0.0.1`）或公開 Coordinator
5. 刪除使用者資料、降低安全預設、匯出未遮蔽憑證
6. `git push --force`、略過 hooks、或變更 branch protection

PR 標籤建議：`high-risk`（人工核准後才可合併）。

## 4. Evidence 紀律

- 勾選 checklist 前必須有真實測試輸出或審查紀錄。
- 禁止空勾、禁止刪測試以換取通過。
- 未驗證假設不得標為 VERIFIED／完成。
