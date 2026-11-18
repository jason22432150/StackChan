"""
Raspberry Pi Coordinator：個人版最小 HTTP 服務。

提供：
- GET  /healthz              容器健康檢查（不含密鑰）
- POST /v1/events/batch      Bridge 批次匯入（先寫入 SQLite 再 ACK）
- GET  /v1/sync/status       查詢連續 ACK 游標與缺口

刻意保持精簡：stdlib HTTP、單一 Bridge Token、可選 TLS。
完整配對／Dashboard／CoreS3 stream 不在本模組。
"""

from __future__ import annotations

import json
import ssl
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from stackchan.contracts import AuthorizationError, Principal
from stackchan.contracts.authz import ApiGate, TokenDirectory
from stackchan.coordinator import CoordinatorStore, CoordinatorStoreError
from stackchan.sync.coordinator_api import CoordinatorSyncApi, SyncFailClosedError
from stackchan.sync.models import BatchInput


@dataclass(frozen=True, slots=True)
class PiCoordinatorConfig:
    """Pi Coordinator 執行設定。"""

    db_path: Path
    bridge_id: str
    bridge_token: str
    host: str = "0.0.0.0"
    port: int = 8443
    tls_cert: Path | None = None
    tls_key: Path | None = None


def build_bridge_token_directory(*, bridge_id: str, bridge_token: str) -> TokenDirectory:
    """建立個人版單一 Bridge Token 目錄。"""
    if not bridge_id.strip():
        raise ValueError("bridge_id 不可為空")
    if not bridge_token.strip():
        raise ValueError("bridge_token 不可為空")
    tokens = TokenDirectory()
    tokens.issue(
        bridge_token,
        Principal(
            subject_id=bridge_id,
            subject_type="bridge",
            scopes=frozenset({"bridge:write", "bridge:sync"}),
        ),
    )
    return tokens


class PiCoordinatorApp:
    """把 CoordinatorSyncApi 接到 stdlib HTTP。"""

    def __init__(self, store: CoordinatorStore, api: CoordinatorSyncApi) -> None:
        self.store = store
        self.api = api
        self._lock = threading.RLock()

    def handle(
        self,
        *,
        method: str,
        path: str,
        authorization_header: str | None,
        body: bytes,
        query: dict[str, list[str]],
    ) -> tuple[int, dict[str, Any]]:
        """回傳 (status, JSON object)。"""
        # healthz 不碰 SQLite，可略過鎖以利 Docker healthcheck
        if method == "GET" and path == "/healthz":
            return 200, {
                "status": "ok",
                "service": "stackchan-pi-coordinator",
                "mode": self.api.mode.value,
            }

        with self._lock:
            try:
                if method == "POST" and path == "/v1/events/batch":
                    return self._submit_batch(authorization_header, body)
                if method == "GET" and path == "/v1/sync/status":
                    return self._sync_status(authorization_header, query)
            except AuthorizationError as exc:
                return exc.http_status, {"error": {"code": exc.code, "message": exc.message}}
            except SyncFailClosedError as exc:
                return 503, {
                    "error": {
                        "code": "fail_closed",
                        "message": exc.message,
                        "mode": exc.mode.value,
                    }
                }
            except CoordinatorStoreError as exc:
                return 400, {"error": {"code": "store_error", "message": str(exc)}}
            except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
                return 400, {"error": {"code": "bad_request", "message": str(exc)}}

        return 404, {"error": {"code": "not_found", "message": f"未知路由 {method} {path}"}}

    def _submit_batch(
        self,
        authorization_header: str | None,
        body: bytes,
    ) -> tuple[int, dict[str, Any]]:
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("body 必須為 JSON object")
        batch = BatchInput(
            bridge_id=str(payload["bridge_id"]),
            epoch=str(payload["epoch"]),
            events=list(payload.get("events") or []),
        )
        ack = self.api.submit_event_batch(batch, authorization_header=authorization_header)
        # 規格：先可靠儲存再確認 Bridge
        return 200, ack.to_dict()

    def _sync_status(
        self,
        authorization_header: str | None,
        query: dict[str, list[str]],
    ) -> tuple[int, dict[str, Any]]:
        bridge_id = (query.get("bridge_id") or [""])[0]
        epoch = (query.get("epoch") or [""])[0]
        if not bridge_id or not epoch:
            raise ValueError("bridge_id 與 epoch 為必填 query")
        ack = self.api.get_sync_status(
            bridge_id=bridge_id,
            epoch=epoch,
            authorization_header=authorization_header,
        )
        return 200, ack.to_dict()


def make_handler(app: PiCoordinatorApp) -> type[BaseHTTPRequestHandler]:
    """建立綁定 App 的 RequestHandler 類別。"""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            # 避免把 Authorization 寫進預設 stderr access log
            return

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 1_048_576:
                raise ValueError("Content-Length 不合法")
            if length == 0:
                return b""
            return self.rfile.read(length)

        def _dispatch(self, method: str) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query, keep_blank_values=False)
            try:
                body = self._read_body() if method in {"POST", "PUT", "PATCH"} else b""
            except ValueError as exc:
                status, payload = 400, {"error": {"code": "bad_request", "message": str(exc)}}
            else:
                status, payload = app.handle(
                    method=method,
                    path=parsed.path,
                    authorization_header=self.headers.get("Authorization"),
                    body=body,
                    query=query,
                )
            data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

    return Handler


def create_pi_server(config: PiCoordinatorConfig) -> tuple[ThreadingHTTPServer, CoordinatorStore, PiCoordinatorApp]:
    """建立已綁定的 Pi Coordinator HTTP server（呼叫端負責 serve_forever／shutdown）。"""
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    store = CoordinatorStore(config.db_path, check_same_thread=False)
    tokens = build_bridge_token_directory(bridge_id=config.bridge_id, bridge_token=config.bridge_token)
    api = CoordinatorSyncApi(store, ApiGate(tokens))
    app = PiCoordinatorApp(store, api)
    server = ThreadingHTTPServer((config.host, config.port), make_handler(app))
    if config.tls_cert is not None or config.tls_key is not None:
        if config.tls_cert is None or config.tls_key is None:
            server.server_close()
            store.close()
            raise ValueError("TLS 需要同時提供 cert 與 key")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(config.tls_cert, config.tls_key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    return server, store, app


def serve_pi_forever(config: PiCoordinatorConfig) -> None:
    """阻塞執行 Pi Coordinator。"""
    server, store, _app = create_pi_server(config)
    host, port = server.server_address[:2]
    scheme = "https" if config.tls_cert else "http"
    print(
        f"Pi Coordinator ready on {scheme}://{host}:{port} "
        f"(sqlite={config.db_path}, bridge_id={config.bridge_id})",
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        store.close()
