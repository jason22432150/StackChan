"""
個人版裝置 → Pi：拉取待派送通知（HTTP）。

不燒錄、不直連 Avatar／Servo；供 host 驗收與日後 CoreS3 對接。
"""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen


class DevicePullError(RuntimeError):
    """裝置 pull 失敗（網路／授權／契約）。"""


@dataclass(frozen=True, slots=True)
class PendingPullResult:
    """一次 pending pull 結果（僅摘要欄位）。"""

    device_id: str
    items: list[dict[str, Any]]
    ok: bool
    error: str | None = None


@dataclass(slots=True)
class DevicePullClient:
    """對 `GET /v1/devices/{device_id}/notifications/pending` 的 HTTP 客戶端。"""

    base_url: str
    device_id: str
    device_token: str
    timeout_seconds: float = 10.0
    ca_file: Path | None = None
    insecure_skip_verify: bool = False

    def __post_init__(self) -> None:
        base = self.base_url.strip().rstrip("/")
        if not base:
            raise ValueError("base_url 不可為空")
        if not (base.startswith("http://") or base.startswith("https://")):
            raise ValueError("base_url 必須以 http:// 或 https:// 開頭")
        if not self.device_id.strip():
            raise ValueError("device_id 不可為空")
        if not self.device_token.strip():
            raise ValueError("device_token 不可為空")
        if self.insecure_skip_verify and self.ca_file is not None:
            raise ValueError("不可同時指定 ca_file 與 insecure_skip_verify")
        self.base_url = base
        self.device_id = self.device_id.strip()
        self.device_token = self.device_token.strip()

    def pull_pending(self, *, limit: int = 50) -> PendingPullResult:
        """拉取未過期 pending；失敗時 raise DevicePullError。"""
        if not 1 <= limit <= 100:
            raise ValueError("limit 必須在 1..100")
        path = f"v1/devices/{quote(self.device_id, safe='')}/notifications/pending"
        url = urljoin(self.base_url + "/", path) + "?" + urlencode({"limit": str(limit)})
        request = Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.device_token}",
                "User-Agent": "stackchan-device-pull/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds, context=self._ssl_context()) as response:
                raw = response.read()
                status = getattr(response, "status", 200)
        except HTTPError as exc:
            detail = _read_error_body(exc)
            if exc.code == 401:
                raise DevicePullError(f"unauthorized:{detail}") from exc
            if exc.code == 403:
                raise DevicePullError(f"forbidden:{detail}") from exc
            raise DevicePullError(f"http_{exc.code}:{detail}") from exc
        except URLError as exc:
            raise DevicePullError(f"network_error:{exc.reason}") from exc
        except TimeoutError as exc:
            raise DevicePullError("timeout") from exc

        if status >= 400:
            raise DevicePullError(f"http_{status}")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DevicePullError("invalid_json") from exc
        if not isinstance(payload, dict) or "items" not in payload:
            raise DevicePullError("invalid_payload")
        items = payload.get("items")
        if not isinstance(items, list):
            raise DevicePullError("invalid_items")
        # 僅保留摘要鍵，避免日後誤帶 Prompt。
        safe_items = [_summarize_intent(item) for item in items if isinstance(item, dict)]
        return PendingPullResult(device_id=self.device_id, items=safe_items, ok=True, error=None)

    def _ssl_context(self) -> ssl.SSLContext | None:
        if self.base_url.startswith("http://"):
            return None
        if self.insecure_skip_verify:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        if self.ca_file is not None:
            return ssl.create_default_context(cafile=str(self.ca_file))
        return ssl.create_default_context()


def _summarize_intent(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "delivery_id",
        "notification_id",
        "device_id",
        "priority",
        "expires_at",
        "policy_version",
        "generation",
        "presentation_profile",
        "event_ids",
    )
    out: dict[str, Any] = {}
    for key in keys:
        if key in item:
            out[key] = item[key]
    return out


def _read_error_body(exc: HTTPError) -> str:
    try:
        raw = exc.read()
    except OSError:
        return exc.reason or "error"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return exc.reason or "error"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text[:200]
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("code") or text[:200])
    return text[:200]
