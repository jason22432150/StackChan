"""pytest fixtures。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import app


@pytest.fixture()
def example_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config.example.yaml"


@pytest.fixture()
def settings(example_config_path: Path):
    return load_settings(example_config_path)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, example_config_path: Path):
    """使用暫存 DB，避免污染開發資料。"""
    import app.main as main_mod

    settings = load_settings(example_config_path)
    settings.storage.db_path = str(tmp_path / "companion-test.db")
    monkeypatch.setattr(main_mod, "_settings", settings)
    with TestClient(app) as test_client:
        yield test_client
