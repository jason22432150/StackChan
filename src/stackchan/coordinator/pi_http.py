"""
Raspberry Pi Coordinator：個人版最小 HTTP 服務。

提供：
- GET  /healthz              容器健康檢查（不含密鑰）
- GET  /dashboard            簡易唯讀管理頁（HTML；Token 由瀏覽器送出）
- POST /v1/events/batch      Bridge 批次匯入（先寫入 SQLite 再 ACK）
- GET  /v1/events            近期事件摘要（需 dashboard:read；不含 Prompt）
- GET  /v1/notifications/pending  待派送通知佇列（TTL／優先）
- GET  /v1/sync/status       查詢連續 ACK 游標與缺口

刻意保持精簡：stdlib HTTP、單一 Bridge Token、可選 TLS。
個人版：同一 Bridge Token 兼具 bridge:write／bridge:sync／dashboard:read
（單管理員、單 Bridge）；管理頁事件列表僅回傳該 bridge_id 摘要。
完整配對／CoreS3 WebSocket stream 不在本模組（佇列先落地供後續 stream 取用）。
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

from stackchan.contracts import AuthorizationError, ContractValidationError, Principal
from stackchan.contracts.authz import ApiGate, TokenDirectory, load_route_requirements
from stackchan.coordinator import CoordinatorStore, CoordinatorStoreError
from stackchan.coordinator.personal_notify import build_personal_notification_intent
from stackchan.coordinator.pi_dashboard import render_dashboard_html, summarize_event_row
from stackchan.sync.coordinator_api import CoordinatorSyncApi, SyncFailClosedError
from stackchan.sync.models import BatchInput

load_route_requirements.cache_clear()


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
    device_id: str = "cores3_primary"
    policy_version: str = "personal-v1"
    generation: int = 1
    notify_ttl_seconds: int = 600


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
            scopes=frozenset({"bridge:write", "bridge:sync", "dashboard:read"}),
        ),
    )
    return tokens


class PiCoordinatorApp:
    """把 CoordinatorSyncApi 接到 stdlib HTTP。"""

    def __init__(
        self,
        store: CoordinatorStore,
        api: CoordinatorSyncApi,
        *,
        device_id: str = "cores3_primary",
        policy_version: str = "personal-v1",
        generation: int = 1,
        notify_ttl_seconds: int = 600,
    ) -> None:
        self.store = store
        self.api = api
        self.device_id = device_id
        self.policy_version = policy_version
        self.generation = generation
        self.notify_ttl_seconds = notify_ttl_seconds
        self._lock = threading.RLock()

    def handle(
        self,
        *,
        method: str,
        path: str,
        authorization_header: str | None,
        body: bytes,
        query: dict[str, list[str]],
    ) -> tuple[int, Any, str]:
        """回傳 (status, body, content_type)。JSON body 為 dict；dashboard 為 HTML str。"""
        # healthz／dashboard 殼層不碰 SQLite，可略過鎖以利 Docker healthcheck
        if method == "GET" and path == "/healthz":
            return 200, {
                "status": "ok",
                "service": "stackchan-pi-coordinator",
                "mode": self.api.mode.value,
            }, "application/json"
        if method == "GET" and path == "/dashboard":
            return 200, render_dashboard_html(), "text/html; charset=utf-8"

        with self._lock:
            try:
                if method == "POST" and path == "/v1/events/batch":
                    status, payload = self._submit_batch(authorization_header, body)
                    return status, payload, "application/json"
                if method == "GET" and path == "/v1/events":
                    status, payload = self._list_events(authorization_header, query)
                    return status, payload, "application/json"
                if method == "GET" and path == "/v1/notifications/pending":
                    status, payload = self._list_pending_notifications(authorization_header, query)
                    return status, payload, "application/json"
                if method == "GET" and path == "/v1/sync/status":
                    status, payload = self._sync_status(authorization_header, query)
                    return status, payload, "application/json"
            except AuthorizationError as exc:
                return (
                    exc.http_status,
                    {"error": {"code": exc.code, "message": exc.message}},
                    "application/json",
                )
            except SyncFailClosedError as exc:
                return (
                    503,
                    {
                        "error": {
                            "code": "fail_closed",
                            "message": exc.message,
                            "mode": exc.mode.value,
                        }
                    },
                    "application/json",
                )
            except CoordinatorStoreError as exc:
                return 400, {"error": {"code": "store_error", "message": str(exc)}}, "application/json"
            except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
                return 400, {"error": {"code": "bad_request", "message": str(exc)}}, "application/json"

        return (
            404,
            {"error": {"code": "not_found", "message": f"未知路由 {method} {path}"}},
            "application/json",
        )

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
        # 規格：先可靠儲存再確認 Bridge；接受的事件進入個人版待派送佇列。
        accepted = set(ack.accepted_event_ids)
        for raw in batch.events:
            if not isinstance(raw, dict):
                continue
            event_id = str(raw.get("event_id", ""))
            if event_id not in accepted:
                continue
            try:
                intent = build_personal_notification_intent(
                    raw,
                    device_id=self.device_id,
                    policy_version=self.policy_version,
                    generation=self.generation,
                    ttl_seconds=self.notify_ttl_seconds,
                )
                self.store.enqueue_pending_notification(intent)
            except (ValueError, CoordinatorStoreError, ContractValidationError, KeyError, TypeError):
                # 佇列失敗不回滾已 ACK 的 Bridge 寫入；下輪可由管理頁／重送策略補。
                continue
        return 200, ack.to_dict()

    def _list_events(
        self,
        authorization_header: str | None,
        query: dict[str, list[str]],
    ) -> tuple[int, dict[str, Any]]:
        # OpenAPI：GET /v1/events 需 dashboard:read；個人版只回摘要欄位。
        principal = self.api.gate.authorize("GET", "/v1/events", authorization_header)
        if principal is None:
            raise AuthorizationError("unauthorized", "缺少或無效的 Bearer token", http_status=401)
        raw_limit = (query.get("limit") or ["50"])[0]
        try:
            limit = int(raw_limit)
        except ValueError as exc:
            raise ValueError("limit 必須為整數") from exc
        if not 1 <= limit <= 100:
            raise ValueError("limit 必須在 1..100")
        # Bridge principal 只可見自己的事件；其他 subject 暫不開放跨橋讀取。
        scope_bridge = principal.subject_id if principal.subject_type == "bridge" else None
        rows = self.store.list_recent_event_summaries(limit=limit, bridge_id=scope_bridge)
        items = [summarize_event_row(row) for row in rows]
        return 200, {"items": items, "next_cursor": None}

    def _list_pending_notifications(
        self,
        authorization_header: str | None,
        query: dict[str, list[str]],
    ) -> tuple[int, dict[str, Any]]:
        self.api.gate.authorize("GET", "/v1/notifications/pending", authorization_header)
        raw_limit = (query.get("limit") or ["50"])[0]
        try:
            limit = int(raw_limit)
        except ValueError as exc:
            raise ValueError("limit 必須為整數") from exc
        items = self.store.list_pending_notifications(limit=limit)
        return 200, {"items": items}

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
                status: int = 400
                payload: Any = {"error": {"code": "bad_request", "message": str(exc)}}
                content_type = "application/json"
            else:
                status, payload, content_type = app.handle(
                    method=method,
                    path=parsed.path,
                    authorization_header=self.headers.get("Authorization"),
                    body=body,
                    query=query,
                )
            if content_type.startswith("text/html"):
                data = str(payload).encode("utf-8")
                ctype = content_type
            else:
                data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
                ctype = "application/json; charset=utf-8"
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            if content_type.startswith("text/html"):
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                    "connect-src 'self'; img-src 'none'; base-uri 'none'; form-action 'none'",
                )
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
    app = PiCoordinatorApp(
        store,
        api,
        device_id=config.device_id,
        policy_version=config.policy_version,
        generation=config.generation,
        notify_ttl_seconds=config.notify_ttl_seconds,
    )
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
