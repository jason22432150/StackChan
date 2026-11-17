"""Loopback TLS transport for manually approved CoreS3 pairing."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import ssl
from asyncio import StreamReader, StreamWriter
from collections.abc import Awaitable
from datetime import datetime, timezone
from http import HTTPStatus

from stackchan.contracts.authz import ApiGate, AuthorizationError
from stackchan.coordinator.policy_lease_server import _error_body, _http_response
from stackchan.security.pairing import PairingError, PairingService

_START = "/v1/pairing/sessions"
_SESSION = re.compile(r"/v1/pairing/sessions/(pair_[0-9a-f]{16})/(confirm|complete)")
_CLAIM = "x-stackchan-pairing-claim"
_MAX_PENDING = 32
_MAX_REQUEST_BYTES = 4096


async def _read_request(reader: StreamReader) -> tuple[str, str, dict[str, str], bytes]:
    header = await reader.readuntil(b"\r\n\r\n")
    line, *fields = header[:-4].decode("ascii").split("\r\n")
    method, path, version = line.split(" ")
    if version != "HTTP/1.1":
        raise ValueError("unsupported protocol")
    headers: dict[str, str] = {}
    for field in fields:
        name, colon, value = field.partition(":")
        name = name.lower()
        if not colon or not re.fullmatch(r"[a-z0-9-]+", name) or name in headers:
            raise ValueError("invalid header")
        headers[name] = value.strip(" \t")
    length = headers.get("content-length", "0")
    if "transfer-encoding" in headers or not re.fullmatch(r"[0-9]{1,4}", length):
        raise ValueError("invalid body framing")
    size = int(length)
    if size > _MAX_REQUEST_BYTES:
        raise ValueError("body too large")
    return method, path, headers, await reader.readexactly(size)


class _PairingRoutes:
    def __init__(self, service: PairingService, gate: ApiGate, device_policy: tuple[str, str] | None) -> None:
        self.service = service
        self.gate = gate
        self.device_policy = device_policy
        self.claims: dict[str, tuple[bytes, datetime]] = {}

    def dispatch(self, method: str, path: str, headers: dict[str, str], body: bytes) -> bytes:
        status, payload, claim = self._dispatch(method, path, headers, body)
        response = _http_response(status, payload, content_type="application/json", no_store=True)
        if claim is not None:
            head, delimiter, content = response.partition(b"\r\n\r\n")
            response = head + b"\r\nX-StackChan-Pairing-Claim: " + claim.encode("ascii") + delimiter + content
        return response

    def _dispatch(
        self, method: str, path: str, headers: dict[str, str], body: bytes,
    ) -> tuple[HTTPStatus, bytes, str | None]:
        match = _SESSION.fullmatch(path)
        if path != _START and match is None:
            return HTTPStatus.NOT_FOUND, _error_body("not_found", "unknown path"), None
        if method != "POST":
            return HTTPStatus.METHOD_NOT_ALLOWED, _error_body("invalid_request", "only POST is supported"), None
        now = datetime.now(timezone.utc)
        self.claims = {key: item for key, item in self.claims.items() if item[1] > now}
        claim = None
        try:
            if match and match.group(2) == "complete":
                if body:
                    raise ValueError("complete does not accept a body")
                pairing_id = match.group(1)
                supplied = headers.get(_CLAIM, "")
                expected = self.claims.get(pairing_id)
                if expected is None or not hmac.compare_digest(expected[0], hashlib.sha256(supplied.encode("ascii")).digest()):
                    return HTTPStatus.UNAUTHORIZED, _error_body("unauthorized", "invalid pairing claim"), None
                result = self.service.complete(pairing_id, device_policy=self.device_policy)
                del self.claims[pairing_id]
            else:
                if match:
                    principal = self.gate.authorize(method, path, headers.get("authorization"))
                    if principal is None:
                        return HTTPStatus.UNAUTHORIZED, _error_body("unauthorized", "administrator required"), None
                if headers.get("content-type") != "application/json":
                    raise ValueError("JSON required")
                request = json.loads(body.decode("utf-8"))
                if not isinstance(request, dict):
                    raise ValueError("JSON object required")
                if match:
                    if request.get("pairing_id") != match.group(1):
                        raise ValueError("pairing ID mismatch")
                    if match.group(1) not in self.claims:
                        raise PairingError("pairing is no longer active")
                    result = self.service.confirm(request, admin=principal)
                    if result["error"] == "forbidden":
                        self.claims.pop(match.group(1), None)
                else:
                    if request.get("subject_type") != "device":
                        raise ValueError("device pairing required")
                    if len(self.claims) >= _MAX_PENDING:
                        return HTTPStatus.CONFLICT, _error_body("conflict", "too many pending pairings"), None
                    result = self.service.start(request)
                    claim = secrets.token_urlsafe(32)
                    self.claims[result["pairing_id"]] = (
                        hashlib.sha256(claim.encode("ascii")).digest(), datetime.fromisoformat(result["expires_at"]),
                    )
        except AuthorizationError as exc:
            return HTTPStatus(exc.http_status), _error_body(exc.code, "pairing authorization refused"), None
        except PairingError:
            return HTTPStatus.FORBIDDEN, _error_body("forbidden", "pairing refused"), None
        except (ValueError, RecursionError):
            return HTTPStatus.BAD_REQUEST, _error_body("invalid_request", "invalid pairing request"), None
        return HTTPStatus.OK, json.dumps(result, separators=(",", ":")).encode("utf-8"), claim


def serve_device_pairing(
    service: PairingService, gate: ApiGate, tls: ssl.SSLContext, *, port: int,
    device_policy: tuple[str, str] | None = None,
) -> Awaitable[asyncio.Server]:
    """Bind a loopback TLS listener with an optional operator-selected policy ID and version."""
    if tls.protocol != ssl.PROTOCOL_TLS_SERVER or tls.minimum_version < ssl.TLSVersion.TLSv1_2:
        raise ValueError("device pairing requires TLS 1.2 or newer")
    routes = _PairingRoutes(service, gate, device_policy)

    async def client_connected(reader: StreamReader, writer: StreamWriter) -> None:
        try:
            async with asyncio.timeout(5):
                try:
                    response = routes.dispatch(*await _read_request(reader))
                except (ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
                    response = _http_response(
                        HTTPStatus.BAD_REQUEST, _error_body("invalid_request", "malformed HTTP request"),
                        content_type="application/json", no_store=True,
                    )
                writer.write(response)
                await writer.drain()
        except (TimeoutError, OSError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    return asyncio.start_server(
        client_connected, host="127.0.0.1", port=port, ssl=tls,
        limit=_MAX_REQUEST_BYTES, ssl_handshake_timeout=5, ssl_shutdown_timeout=2,
    )
