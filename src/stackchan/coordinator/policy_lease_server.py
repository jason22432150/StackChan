"""Loopback TLS HTTP transport for GET /v1/devices/{deviceId}/policy."""

from __future__ import annotations

import asyncio
import json
import re
import ssl
from asyncio import StreamReader, StreamWriter
from collections.abc import Awaitable
from http import HTTPStatus

from stackchan.contracts.authz import AuthorizationError
from stackchan.coordinator.policy_lease import DevicePolicyLeaseService

_POLICY_PATH = re.compile(r"^/v1/devices/([^/]+)/policy$")
_MAX_HEADER_BYTES = 4096
_ERROR_CODES = frozenset({
    "unauthorized",
    "forbidden",
    "invalid_request",
    "not_found",
    "conflict",
    "policy_invalid",
    "revoked",
    "unsupported_schema_version",
})


def _http_response(status: HTTPStatus, body: bytes, *, content_type: str) -> bytes:
    headers = (
        f"HTTP/1.1 {status.value} {status.phrase}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    return headers + body


def _error_body(code: str, message: str) -> bytes:
    error = code if code in _ERROR_CODES else "invalid_request"
    return json.dumps(
        {"schema_version": "0.1", "error": error, "message": message[:512]},
        separators=(",", ":"),
    ).encode("utf-8")


async def _read_request(reader: StreamReader) -> tuple[str, str, dict[str, str]] | None:
    raw = bytearray()
    while b"\r\n\r\n" not in raw and len(raw) <= _MAX_HEADER_BYTES:
        chunk = await reader.read(256)
        if not chunk:
            break
        raw.extend(chunk)
    if b"\r\n\r\n" not in raw or len(raw) > _MAX_HEADER_BYTES:
        return None
    header_text = raw.split(b"\r\n\r\n", 1)[0].decode("ascii", errors="strict")
    lines = header_text.split("\r\n")
    if not lines:
        return None
    parts = lines[0].split()
    if len(parts) != 3:
        return None
    method, target, version = parts
    if version != "HTTP/1.1":
        return None
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if not sep or name.lower() in headers:
            return None
        headers[name.lower()] = value.lstrip()
    return method, target, headers


async def _handle_client(
    reader: StreamReader,
    writer: StreamWriter,
    leases: DevicePolicyLeaseService,
) -> None:
    try:
        parsed = await _read_request(reader)
        if parsed is None:
            writer.write(_http_response(
                HTTPStatus.BAD_REQUEST,
                _error_body("invalid_request", "malformed HTTP/1.1 request"),
                content_type="application/json",
            ))
            return
        method, target, headers = parsed
        path = target.split("?", 1)[0]
        match = _POLICY_PATH.match(path)
        if method != "GET":
            writer.write(_http_response(
                HTTPStatus.METHOD_NOT_ALLOWED,
                _error_body("invalid_request", "only GET is supported"),
                content_type="application/json",
            ))
            return
        if match is None:
            writer.write(_http_response(
                HTTPStatus.NOT_FOUND,
                _error_body("not_found", "unknown path"),
                content_type="application/json",
            ))
            return
        device_id = match.group(1)
        try:
            lease = leases.get_device_policy(
                device_id,
                authorization_header=headers.get("authorization"),
            )
        except AuthorizationError as exc:
            writer.write(_http_response(
                HTTPStatus(exc.http_status),
                _error_body(exc.code, exc.message),
                content_type="application/json",
            ))
            return
        body = json.dumps(lease.as_openapi_policy(), separators=(",", ":")).encode("utf-8")
        writer.write(_http_response(HTTPStatus.OK, body, content_type="application/json"))
    except (UnicodeDecodeError, ConnectionResetError, asyncio.IncompleteReadError):
        try:
            writer.write(_http_response(
                HTTPStatus.BAD_REQUEST,
                _error_body("invalid_request", "request aborted"),
                content_type="application/json",
            ))
        except OSError:
            pass
    finally:
        try:
            await writer.drain()
        except OSError:
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


def serve_device_policy(
    leases: DevicePolicyLeaseService,
    tls: ssl.SSLContext,
    *,
    port: int,
) -> Awaitable[asyncio.Server]:
    """Return an awaitable 127.0.0.1 TLS server (use: async with await serve_device_policy(...))."""
    if tls.protocol != ssl.PROTOCOL_TLS_SERVER or tls.minimum_version < ssl.TLSVersion.TLSv1_2:
        raise ValueError("device policy requires a TLS server context with TLS 1.2 or newer")

    async def _client_connected(reader: StreamReader, writer: StreamWriter) -> None:
        await _handle_client(reader, writer, leases)

    return asyncio.start_server(
        _client_connected,
        host="127.0.0.1",
        port=port,
        ssl=tls,
    )
