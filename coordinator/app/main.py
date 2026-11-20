"""FastAPI 入口：健康檢查與設定讀取（Phase 0）。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import __version__
from app.config import Settings, load_settings
from app.device_ws import DeviceWsHub
from app.providers import get_provider
from app.storage import Storage

_settings: Settings | None = None
_storage: Storage | None = None
_device_hub = DeviceWsHub()


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _storage
    settings = get_settings()
    _storage = Storage(settings.storage.db_path)
    try:
        yield
    finally:
        if _storage is not None:
            _storage.close()
            _storage = None


app = FastAPI(
    title="StackChan Companion Coordinator",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    interests = _storage.list_interests() if _storage else {}
    return {
        "ok": True,
        "service": "stackchan-companion-coordinator",
        "version": __version__,
        "phase": 0,
        "active_llm_provider": settings.llm.active_provider,
        "providers": settings.llm.providers,
        "device_can_push": _device_hub.can_push_companion_ui(),
        "interest_count": len(interests),
        "schema_version": _storage.get_schema_version() if _storage else None,
    }


@app.get("/api/config")
async def read_config() -> JSONResponse:
    """讀取公開設定。Phase 0 不做寫入／認證；後續 Phase 再加驗證。"""
    return JSONResponse(get_settings().public_dict())


@app.get("/api/providers/active/ping")
async def ping_active_provider() -> dict[str, Any]:
    """以 mock Provider 驗證介面可呼叫（不連外）。"""
    settings = get_settings()
    provider = get_provider(settings.llm.active_provider)
    reply = await provider.generate_reply({}, "ping")
    action = await provider.choose_pet_action({"energy": 70})
    return {
        "provider": provider.name,
        "reply": reply.text,
        "pet_action": action.action,
    }


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        log_level=settings.app.log_level.lower(),
    )


if __name__ == "__main__":
    run()
