"""對外網路暴露預設與診斷遮蔽。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# Coordinator／Bridge 本機服務預設只綁 loopback；不得預設 0.0.0.0
DEFAULT_BIND_HOST = "127.0.0.1"

_SECRET_KEYS = {
    "access_token",
    "token",
    "password",
    "api_key",
    "authorization",
    "client_public_key",
    "secret",
    "refresh_token",
}


class ExposureError(ValueError):
    """不安全的網路暴露設定。"""


def assert_safe_bind_host(host: str, *, allow_lan: bool = False) -> str:
    """
    檢查綁定位址。

    預設拒絕 0.0.0.0／::／空字串。allow_lan=True 時仍拒絕全網卡綁定，
    僅允許明確單一位址（需部署者自覺）。
    """
    normalized = (host or "").strip().lower()
    if normalized in {"", "0.0.0.0", "::", "[::]"}:
        raise ExposureError(
            f"拒絕綁定 {host!r}；預設僅允許 loopback（{DEFAULT_BIND_HOST}）"
        )
    if not allow_lan and normalized not in {"127.0.0.1", "localhost", "::1"}:
        raise ExposureError(
            f"未授權 LAN 綁定 {host!r}；請顯式 allow_lan=True 或使用 {DEFAULT_BIND_HOST}"
        )
    return host


def redact_secrets(payload: Any) -> Any:
    """遞迴遮蔽敏感欄位，供診斷匯出（永不輸出明文 token）。"""
    if isinstance(payload, dict):
        redacted: dict[str, Any] = {}
        for key, value in payload.items():
            if str(key).lower() in _SECRET_KEYS:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_secrets(value)
        return redacted
    if isinstance(payload, list):
        return [redact_secrets(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(redact_secrets(item) for item in payload)
    return deepcopy(payload) if isinstance(payload, (dict, list)) else payload
