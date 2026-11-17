"""Loopback TLS WebSocket transport for Coordinator device notifications."""

from __future__ import annotations

import asyncio
import ssl
from datetime import datetime, timezone
from http import HTTPStatus
from math import isfinite
from sqlite3 import Error as DatabaseError

from websockets.asyncio.server import ServerConnection, serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

from stackchan.contracts.validate import ContractValidationError
from stackchan.coordinator.device_stream import encode_heartbeat, encode_notification_intent
from stackchan.coordinator.dispatch import NotificationDispatcher
from stackchan.coordinator.policy_lease import DevicePolicyLeaseService
from stackchan.coordinator.policy_lease_server import build_device_policy_response


def _device_credentials(headers: Headers) -> tuple[str, str, str] | None:
    auth = headers.get_all("Authorization")
    devices = headers.get_all("X-StackChan-Device-Id")
    versions = headers.get_all("X-StackChan-Policy-Version")
    if len(auth) != 1 or len(devices) != 1 or len(versions) != 1:
        return None
    parts = auth[0].split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    if not all(1 <= len(value) <= 128 and value.isascii() and value.isprintable()
               for value in (devices[0], versions[0])):
        return None
    return devices[0], parts[1], versions[0]


def serve_device_stream(
    dispatcher: NotificationDispatcher,
    tls: ssl.SSLContext,
    *,
    port: int,
    generation: int,
    heartbeat_interval: float,
    pong_timeout: float,
    policy_leases: DevicePolicyLeaseService | None = None,
) -> serve:
    """Create a loopback TLS server, optionally serving device policy on the same port."""
    if tls.protocol != ssl.PROTOCOL_TLS_SERVER or tls.minimum_version < ssl.TLSVersion.TLSv1_2:
        raise ValueError("device stream requires a TLS server context with TLS 1.2 or newer")
    if not all(isfinite(value) and value > 0 for value in (heartbeat_interval, pong_timeout)):
        raise ValueError("heartbeat intervals must be finite and positive")
    if heartbeat_interval < 0.001:
        raise ValueError("heartbeat interval must be at least one millisecond")
    if type(generation) is not int or not 0 <= generation < (1 << 64):
        raise ValueError("device stream generation must be a uint64")

    def process_request(socket: ServerConnection, request: Request) -> Response | None:
        if request.path != "/v1/device-stream":
            if policy_leases is not None:
                authorization = request.headers.get_all("Authorization")
                try:
                    policy = build_device_policy_response(
                        policy_leases, request.path, authorization[0] if len(authorization) == 1 else None,
                        method=request.method, protocol=request.protocol,
                    )
                except DatabaseError:
                    return socket.respond(HTTPStatus.SERVICE_UNAVAILABLE, "Unavailable\n")
                if policy is not None:
                    status, body = policy
                    return Response(
                        status.value,
                        status.phrase,
                        Headers([
                            ("Content-Type", "application/json"),
                            ("Content-Length", str(len(body))),
                            ("Connection", "close"),
                        ]),
                        body,
                    )
            return socket.respond(HTTPStatus.NOT_FOUND, "Not Found\n")
        credentials = _device_credentials(request.headers)
        try:
            if credentials is not None and dispatcher.can_connect(*credentials):
                return None
        except DatabaseError:
            return socket.respond(HTTPStatus.SERVICE_UNAVAILABLE, "Unavailable\n")
        return socket.respond(HTTPStatus.UNAUTHORIZED, "Unauthorized\n")

    async def handle(socket: ServerConnection) -> None:
        request = socket.request
        credentials = _device_credentials(request.headers) if request is not None else None
        if credentials is None:
            await socket.close(1008, "Unauthorized")
            return
        device, token, policy = credentials
        try:
            session = dispatcher.connect(device, token, policy)
        except DatabaseError:
            await socket.close(1011, "Authorization unavailable")
            return
        if session is None:
            await socket.close(1008, "Unauthorized")
            return
        try:
            last_sent: datetime | None = None
            while True:
                pong = await socket.ping()
                await asyncio.wait_for(pong, pong_timeout)
                if not dispatcher.heartbeat(device, session, token):
                    await socket.close(1008, "Session expired")
                    return
                sent = datetime.now(timezone.utc)
                sent_ms = sent.replace(microsecond=(sent.microsecond // 1000) * 1000)
                if last_sent is not None and sent_ms <= last_sent:
                    await socket.close(1011, "Clock unavailable")
                    return
                last_sent = sent_ms
                await socket.send(encode_heartbeat(
                    device_id=device, policy_version=policy, generation=generation, sent_at=sent,
                ), text=True)
                intent = dispatcher.take_next(device, session, token, generation=generation)
                if intent is not None:
                    await socket.send(encode_notification_intent(intent, sent_at=datetime.now(timezone.utc)), text=True)
                try:
                    await asyncio.wait_for(socket.recv(), heartbeat_interval)
                except TimeoutError:
                    continue
                await socket.close(1008, "Unexpected device message")
                return
        except TimeoutError:
            await socket.close(1008, "Heartbeat timeout")
        except ContractValidationError:
            await socket.close(1011, "Invalid outbound frame")
        except ConnectionClosed:
            pass
        finally:
            dispatcher.disconnect(device, session)

    return serve(
        handle, "127.0.0.1", port, ssl=tls, process_request=process_request, origins=[None],
        compression=None, ping_interval=None, max_size=1024, max_queue=1, close_timeout=1,
    )
