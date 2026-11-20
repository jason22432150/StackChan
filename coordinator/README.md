# StackChan Companion Coordinator（Raspberry Pi）

單一 Python 服務：FastAPI + asyncio + SQLite + systemd。  
**Phase 1** 提供健康檢查、設定讀取、裝置 WebSocket（hello／heartbeat／指令下發）、mock Provider。  
不呼叫真實雲端 AI、不做音訊串流。

## 本機執行（開發）

```bash
cd coordinator
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

- `GET /health`
- `WS /ws/device`（可加 `?token=` 或 Header `X-StackChan-Token`）
- `POST /api/device/push`：測試下發 `text.show` / `motion.set` 等

## 設定

- 複製 `config.example.yaml` 為 `config.yaml`（可選）
- `STACKCHAN_DEVICE_TOKEN` 可覆寫 `device.token`
- API Key 只放環境變數或本機 `.env`，**禁止提交 Git**

## 安全

- 僅供信任 LAN；不要 Port Forward
- 無 Companion 活動會話時拒絕 UI／動作推送（模式隔離）
- 不寫入任何 ESP32 eFuse
- Phase 1 不自動部署 systemd、不連真實雲端
