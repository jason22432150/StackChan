"""/health 與設定讀取測試。"""

from __future__ import annotations


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["phase"] == 1
    assert body["interest_count"] == 5
    assert body["schema_version"] == 1
    assert "provider_a" in body["providers"]
    assert "provider_b" in body["providers"]
    assert "device" in body
    assert "can_push" in body["device"]


def test_config_readable(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert body["llm"]["active_provider"] == "provider_a"
    assert body["proactivity"]["voice_max_per_day"] == 3
    assert body["device"]["token"] == ""
    assert "token_configured" in body["device"]
    # 確保回應不含密鑰欄位
    dumped = str(body).lower()
    assert "api_key" not in dumped
    assert "secret" not in dumped
