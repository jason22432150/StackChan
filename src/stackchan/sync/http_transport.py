"""
Bridge → Pi Coordinator 真實 HTTP／HTTPS 傳輸。

個人版最小實作：stdlib urllib，Bearer Token，可選 TLS CA。
Coordinator 離線時拋 SyncTransportError，Bridge 保留 Outbox；絕不直送 CoreS3。
"""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from stackchan.sync.models import BatchAck, BatchInput
from stackchan.sync.transport import SyncTransportError


@dataclass(slots=True)
class HttpSyncTransport:
    """對 Pi Coordinator `/v1/events/batch` 的 HTTP 傳輸。"""

    base_url: str
    timeout_seconds: float = 10.0
    ca_file: Path | None = None
    insecure_skip_verify: bool = False

    def __post_init__(self) -> None:
        base = self.base_url.strip().rstrip("/")
        if not base:
            raise ValueError("base_url 不可為空")
        if not (base.startswith("http://") or base.startswith("https://")):
            raise ValueError("base_url 必須以 http:// 或 https:// 開頭")
        if self.insecure_skip_verify and self.ca_file is not None:
            raise ValueError("不可同時指定 ca_file 與 insecure_skip_verify")
        self.base_url = base

    def submit_batch(
        self,
        batch: BatchInput,
        *,
        authorization_header: str | None,
    ) -> BatchAck:
        if not authorization_header:
            raise SyncTransportError("缺少 Authorization header")
        url = urljoin(self.base_url + "/", "v1/events/batch")
        body = json.dumps(batch.to_dict(), ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": authorization_header,
                "User-Agent": "stackchan-bridge/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds, context=self._ssl_context()) as response:
                raw = response.read()
                status = getattr(response, "status", 200)
        except HTTPError as exc:
            detail = _read_error_body(exc)
            if exc.code in {401, 403}:
                raise SyncTransportError(f"unauthorized:{exc.code}:{detail}") from exc
            if exc.code == 503:
                raise SyncTransportError(f"fail_closed_http:{detail}") from exc
            raise SyncTransportError(f"http_{exc.code}:{detail}") from exc
        except URLError as exc:
            raise SyncTransportError(f"network_error:{exc.reason}") from exc
        except TimeoutError as exc:
            raise SyncTransportError("timeout") from exc

        if status >= 400:
            raise SyncTransportError(f"http_{status}")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SyncTransportError("invalid_json_ack") from exc
        if not isinstance(payload, dict):
            raise SyncTransportError("ack_not_object")
        if "error" in payload and "bridge_id" not in payload:
            error = payload.get("error")
            raise SyncTransportError(f"coordinator_error:{error}")
        try:
            return BatchAck.from_dict(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise SyncTransportError(f"invalid_ack:{exc}") from exc

    def _ssl_context(self) -> ssl.SSLContext | None:
        if not self.base_url.startswith("https://"):
            return None
        if self.insecure_skip_verify:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
        if self.ca_file is not None:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(cafile=str(self.ca_file))
            context.verify_mode = ssl.CERT_REQUIRED
            context.check_hostname = True
            return context
        return ssl.create_default_context()


def _read_error_body(exc: HTTPError) -> str:
    try:
        raw = exc.read()
    except OSError:
        return exc.reason or "error"
    if not raw:
        return exc.reason or "error"
    try:
        payload: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw.decode("utf-8", errors="replace")[:200]
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        message = payload["error"].get("message") or payload["error"].get("code")
        return str(message)
    return str(payload)[:200]
