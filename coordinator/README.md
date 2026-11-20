# StackChan Companion Coordinator（Raspberry Pi）

單一 Python 服務：FastAPI + asyncio + SQLite + systemd。  
**Phase 0** 僅提供健康檢查、設定讀取、Provider 介面與 mock，不呼叫真實雲端 AI。

## 本機執行（開發）

```bash
cd coordinator
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

開啟 `http://127.0.0.1:8765/health` 應回傳 JSON 健康狀態。

## 設定

- 複製 `config.example.yaml` 為 `config.yaml`（可選；未提供時使用內建預設）
- API Key 只放環境變數或本機 `.env`，**禁止提交 Git**

## 安全

- 僅供信任 LAN；不要 Port Forward
- 不寫入任何 ESP32 eFuse
- Phase 0 不自動部署 systemd、不連真實雲端
