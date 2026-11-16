# StackChan Agent 契約版本（P1-01 凍結）

| 項目 | 值 |
|---|---|
| `schema_version`（payload 欄位） | `0.1` |
| 契約狀態 | **FROZEN v0.1**（Gate G1 契約側） |
| 凍結日期 | 2026-11-16 |
| 單一來源目錄 | `docs/stackchan-agent-spec/contracts/` |

## 涵蓋 Schema

| 檔案 | `$id` |
|---|---|
| `agent-event.schema.json` | `https://stackchan.local/contracts/agent-event.schema.json` |
| `notification-intent.schema.json` | `https://stackchan.local/contracts/notification-intent.schema.json` |
| `presentation-receipt.schema.json` | `https://stackchan.local/contracts/presentation-receipt.schema.json` |
| `error.schema.json` | `https://stackchan.local/contracts/error.schema.json` |
| `device-stream-envelope.schema.json` | `https://stackchan.local/contracts/device-stream-envelope.schema.json` |
| `pairing.schema.json` | `https://stackchan.local/contracts/pairing.schema.json` |
| `openapi.yaml` | Coordinator HTTP／WS 契約（含 `x-required-scopes`） |

## 相容規則

1. 接收端**必須**拒絕缺少 `schema_version` 或 `schema_version != "0.1"` 的 payload（本輪不實作升級轉譯）。
2. `additionalProperties: false`：未知欄位一律非法。
3. 語意不變式（應用層，非 JSON Schema 可表達）：`response.completed` **不得**推導為 `task.succeeded`；`evidence_level` 與 `event_type` 獨立。
4. OpenAPI／Error／Pairing／Device Stream Envelope 已於 **P1-02** 凍結契約面；本檔仍不宣稱 HTTP API 已部署或可連線。

## 變更流程

變更凍結 schema 必須：更新本檔、遞增或維持明確的版本決策、補契約測試、經人工核准後才能進入依賴此契約的 Bridge／Coordinator 實作合併。
