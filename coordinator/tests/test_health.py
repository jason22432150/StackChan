"""/health 與設定讀取測試。"""

from __future__ import annotations


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["phase"] == 0
    assert body["interest_count"] == 5
    assert body["schema_version"] == 1
    assert "provider_a" in body["providers"]
    assert "provider_b" in body["providers"]


def test_config_readable(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert body["llm"]["active_provider"] == "provider_a"
    assert body["proactivity"]["voice_max_per_day"] == 3
    # 確保回應不含密鑰欄位
    dumped = str(body).lower()
    assert "api_key" not in dumped
    assert "secret" not in dumped
