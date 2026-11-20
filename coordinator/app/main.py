"""FastAPI 入口：健康檢查、設定、裝置 WebSocket（Phase 1）。"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, Query, WebSocket
from fastapi.responses import JSONResponse

from app import __version__
from app.config import Settings, load_settings
from app.device_ws import DeviceWsHub
from app.protocol import make_envelope, parse_envelope
from app.providers import get_provider
from app.storage import Storage

_settings: Settings | None = None
_storage: Storage | None = None
_device_hub = DeviceWsHub()


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
        # 允許以環境變數覆寫裝置 Token（不寫入 YAML）
        env_token = os.environ.get("STACKCHAN_DEVICE_TOKEN")
        if env_token is not None:
            _settings.device.token = env_token
    return _settings


def get_device_hub() -> DeviceWsHub:
    return _device_hub


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _storage
    settings = get_settings()
    _device_hub.expected_token = settings.device.token
    _device_hub.max_text_chars = settings.device.max_text_chars
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
        "phase": 1,
        "active_llm_provider": settings.llm.active_provider,
        "providers": settings.llm.providers,
        "device": _device_hub.snapshot(),
        "interest_count": len(interests),
        "schema_version": _storage.get_schema_version() if _storage else None,
    }


@app.get("/api/config")
async def read_config() -> JSONResponse:
    """讀取公開設定（隱藏 token）。"""
    data = get_settings().public_dict()
    if "device" in data and isinstance(data["device"], dict):
        token = data["device"].get("token", "")
        data["device"]["token_configured"] = bool(token)
        data["device"]["token"] = ""
    return JSONResponse(data)


@app.get("/api/providers/active/ping")
async def ping_active_provider() -> dict[str, Any]:
    settings = get_settings()
    provider = get_provider(settings.llm.active_provider)
    reply = await provider.generate_reply({}, "ping")
    action = await provider.choose_pet_action({"energy": 70})
    return {
        "provider": provider.name,
        "reply": reply.text,
        "pet_action": action.action,
    }


@app.websocket("/ws/device")
async def device_ws(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    x_stackchan_token: str | None = Header(default=None),
) -> None:
    """StackChan Companion 控制通道。Token 可走 query 或 Header。"""
    await _device_hub.handle_socket(websocket, token=token or x_stackchan_token)


@app.post("/api/device/push")
async def push_to_device(
    body: dict[str, Any],
    x_stackchan_token: str | None = Header(default=None),
) -> JSONResponse:
    """
    開發／測試用：向已連線 Companion 下發控制訊息。
    若設定了 device.token，請求 Header 需帶相同 Token。
    """
    settings = get_settings()
    if settings.device.token:
        if not x_stackchan_token or x_stackchan_token != settings.device.token:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    try:
        if "type" in body and "v" in body:
            envelope = parse_envelope(body)
        else:
            envelope = make_envelope(
                str(body.get("type", "")),
                body.get("payload") if isinstance(body.get("payload"), dict) else {},
            )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "bad_request", "message": str(exc)}, status_code=400)
    result = await _device_hub.push(envelope)
    status = 200 if result.get("ok") else 409
    return JSONResponse(result, status_code=status)


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
