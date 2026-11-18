"""Coordinator CLI：Pi HTTP 服務與既有 CoreS3 bench TLS listener。"""

from __future__ import annotations

import argparse
import asyncio
import http.client
import json
import os
import re
import ssl
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from sqlite3 import Error as DatabaseError
from typing import Sequence

from stackchan.contracts.authz import ApiGate
from stackchan.coordinator.device_stream_server import serve_device_stream, validate_device_listener
from stackchan.coordinator.mvp_dispatcher import create_mvp_notification_dispatcher
from stackchan.coordinator.pairing_admin import confirm_pairing
from stackchan.coordinator.pairing_server import serve_device_pairing, serve_lan_device_pairing, validate_pairing_listener
from stackchan.coordinator.pi_http import PiCoordinatorConfig, serve_pi_forever
from stackchan.coordinator.policy_lease import DevicePolicyLeaseService
from stackchan.coordinator.runtime_limits import CORE_S3_MVP_RUNTIME_LIMITS
from stackchan.security.auth_bridge import StoreBackedTokenDirectory
from stackchan.security.identity import TokenHasher
from stackchan.security.pairing import PairingService
from stackchan.security.policy import PolicyService
from stackchan.security.store import SecurityStore


async def _serve(
    db: Path, pepper: bytes, tls: ssl.SSLContext, port: int, generation: int, host: str, device_ip: str | None,
) -> None:
    with SecurityStore(db, hasher=TokenHasher(pepper), read_only=True) as store:
        tokens = StoreBackedTokenDirectory(store)
        policies = PolicyService(store)
        limits = CORE_S3_MVP_RUNTIME_LIMITS
        async with serve_device_stream(
            create_mvp_notification_dispatcher(tokens, policies),
            tls,
            port=port,
            generation=generation,
            heartbeat_interval=limits.heartbeat_interval_seconds,
            pong_timeout=limits.pong_timeout_seconds,
            policy_leases=DevicePolicyLeaseService(ApiGate(tokens), policies),
            host=host,
            device_ip=device_ip,
        ) as server:
            host, bound_port = server.sockets[0].getsockname()
            print(f"Coordinator ready on {host}:{bound_port} (TLS, generation={generation})", flush=True)
            await server.serve_forever()


async def _serve_pairing(
    db: Path, pepper: bytes, tls: ssl.SSLContext, port: int, policy_id: str, policy_version: str,
    host: str = "127.0.0.1", device_ip: str | None = None, admin_port: int | None = None,
) -> None:
    # Pairing writes grants, but must never create or migrate an operator's database.
    with SecurityStore(db, hasher=TokenHasher(pepper), existing_only=True) as store:
        gate = ApiGate(StoreBackedTokenDirectory(store))
        async with AsyncExitStack() as stack:
            if host == "127.0.0.1":
                server = await stack.enter_async_context(await serve_device_pairing(
                    PairingService(store), gate, tls, port=port, device_policy=(policy_id, policy_version),
                ))
                servers = (server,)
            else:
                servers = await stack.enter_async_context(serve_lan_device_pairing(
                    PairingService(store), gate, tls, host=host, device_ip=device_ip,
                    port=port, admin_port=admin_port, device_policy=(policy_id, policy_version),
                ))
            for index, server in enumerate(servers):
                address, bound_port = server.sockets[0].getsockname()
                label = "Pairing" if index == 0 else "Pairing admin"
                print(f"{label} ready on {address}:{bound_port} (TLS, manual approval required)", flush=True)
            await asyncio.gather(*(server.serve_forever() for server in servers))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stackchan coordinator")
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve_pi = subcommands.add_parser(
        "serve-pi",
        help="Raspberry Pi Coordinator：SQLite 事件匯入 HTTP（個人版最小服務）",
    )
    serve_pi.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("STACKCHAN_COORDINATOR_DB", "/data/coordinator.sqlite3")),
        help="Coordinator SQLite 路徑",
    )
    serve_pi.add_argument("--host", default=os.environ.get("STACKCHAN_LISTEN_HOST", "0.0.0.0"))
    serve_pi.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("STACKCHAN_LISTEN_PORT", "8443")),
    )
    serve_pi.add_argument(
        "--bridge-id",
        default=os.environ.get("STACKCHAN_BRIDGE_ID", "bridge_primary"),
        help="允許寫入的 Bridge ID",
    )
    serve_pi.add_argument(
        "--bridge-token",
        default=os.environ.get("STACKCHAN_BRIDGE_TOKEN", ""),
        help="Bridge Bearer token（也可用環境變數）",
    )
    serve_pi.add_argument(
        "--device-id",
        default=os.environ.get("STACKCHAN_DEVICE_ID", "cores3_primary"),
        help="個人版單一 CoreS3 device_id（pending enqueue／device pull）",
    )
    serve_pi.add_argument(
        "--device-token",
        default=os.environ.get("STACKCHAN_DEVICE_TOKEN", ""),
        help="CoreS3 Device Bearer token（選填；也可用環境變數）",
    )
    serve_pi.add_argument("--cert", type=Path, default=None, help="可選 TLS 憑證 PEM")
    serve_pi.add_argument("--key", type=Path, default=None, help="可選 TLS 私鑰 PEM")
    serve = subcommands.add_parser("serve-device", help="serve CoreS3 policy and stream on one TLS port")
    pairing = subcommands.add_parser("serve-pairing", help="serve manually approved device pairing on loopback TLS")
    for command in (serve, pairing):
        command.add_argument("--security-db", required=True, type=Path, help="existing SecurityStore SQLite file")
        command.add_argument("--cert", required=True, type=Path, help="TLS server certificate chain in PEM format")
        command.add_argument("--key", required=True, type=Path, help="TLS server private key file")
        command.add_argument("--port", required=True, type=int, help="TLS port (0 selects a temporary port)")
    pairing.add_argument("--policy-id", required=True, help="policy ID to bind when issuing the device grant")
    pairing.add_argument("--policy-version", required=True, help="explicit policy version to bind")
    pairing.add_argument("--listen", default="127.0.0.1", help="loopback or a private LAN IPv4 address")
    pairing.add_argument("--device-ip", help="the only peer IPv4 allowed with LAN pairing")
    pairing.add_argument("--admin-port", type=int, help="confirm-only loopback TLS port, required with LAN pairing")
    confirm = subcommands.add_parser("confirm-pairing", help="manually approve or reject a pairing over loopback TLS")
    confirm.add_argument("--port", required=True, type=int, help="local pairing administrator TLS port")
    confirm.add_argument("--ca", required=True, type=Path, help="trusted Coordinator CA PEM")
    confirm.add_argument("--pairing-id", required=True, help="pairing ID from the device challenge")
    confirm.add_argument("--user-code", required=True, help="six-character code verified with the device")
    decision = confirm.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true", help="approve only after checking the device code")
    decision.add_argument("--reject", action="store_true", help="reject this pairing")
    find = subcommands.add_parser("find-pairings", help="read local device pairing IDs matching a device code")
    find.add_argument("--security-db", required=True, type=Path, help="existing local SecurityStore SQLite file")
    find.add_argument("--user-code", required=True, help="six-character code shown on the device")
    serve.add_argument("--generation", required=True, type=int, help="CoreS3 Coordinator generation")
    serve.add_argument("--listen", default="127.0.0.1", help="loopback or a private LAN IPv4 address")
    serve.add_argument("--device-ip", help="the only peer IPv4 allowed with a private LAN listener")
    args = parser.parse_args(argv)
    if args.command == "serve-pi":
        token = args.bridge_token or os.environ.get("STACKCHAN_BRIDGE_TOKEN", "")
        if not token.strip():
            serve_pi.error("必須提供 --bridge-token 或 STACKCHAN_BRIDGE_TOKEN")
        if not 0 <= args.port <= 65535:
            serve_pi.error("--port must be between 0 and 65535")
        cert = args.cert or (
            Path(os.environ["STACKCHAN_TLS_CERT"]) if os.environ.get("STACKCHAN_TLS_CERT") else None
        )
        key = args.key or (
            Path(os.environ["STACKCHAN_TLS_KEY"]) if os.environ.get("STACKCHAN_TLS_KEY") else None
        )
        device_token = args.device_token or os.environ.get("STACKCHAN_DEVICE_TOKEN", "")
        try:
            serve_pi_forever(
                PiCoordinatorConfig(
                    db_path=args.db,
                    bridge_id=args.bridge_id,
                    bridge_token=token,
                    host=args.host,
                    port=args.port,
                    tls_cert=cert,
                    tls_key=key,
                    device_id=args.device_id,
                    device_token=device_token,
                )
            )
        except KeyboardInterrupt:
            return 0
        except (OSError, ValueError) as exc:
            print(f"error: Pi Coordinator 啟動失敗：{exc}", file=sys.stderr)
            return 1
        return 0
    if args.command == "find-pairings":
        if not re.fullmatch(r"[A-Z0-9]{6}", args.user_code):
            find.error("user code must contain six uppercase letters or digits")
        pepper = os.environ.get("STACKCHAN_SECURITY_PEPPER", "")
        if not pepper:
            find.error("set STACKCHAN_SECURITY_PEPPER to the existing store's pepper")
        try:
            with SecurityStore(args.security_db, hasher=TokenHasher(pepper.encode()), read_only=True) as store:
                result = store.find_device_pairings(args.user_code)
        except DatabaseError:
            print("error: could not query the existing security database", file=sys.stderr)
            return 1
        # JSON escapes untrusted display names and terminal control characters.
        print(json.dumps(result, ensure_ascii=True))
        return 0
    if args.command == "confirm-pairing":
        token = os.environ.get("STACKCHAN_PAIRING_ADMIN_TOKEN", "")
        if not token:
            confirm.error("set STACKCHAN_PAIRING_ADMIN_TOKEN to an existing administrator token")
        try:
            confirm_pairing(port=args.port, ca=args.ca, pairing_id=args.pairing_id, user_code=args.user_code,
                            approved=args.approve, admin_token=token)
        except (OSError, ValueError, http.client.HTTPException, RecursionError):
            print("error: pairing confirmation failed; check administrator endpoint, trust and challenge", file=sys.stderr)
            return 1
        print("Pairing approved" if args.approve else "Pairing rejected")
        return 0
    command = serve if args.command == "serve-device" else pairing
    if not 0 <= args.port <= 65535:
        command.error("--port must be between 0 and 65535")
    if args.command == "serve-device":
        if not 0 <= args.generation < (1 << 64):
            serve.error("--generation must be a uint64")
        try:
            validate_device_listener(args.listen, args.device_ip)
        except ValueError as exc:
            serve.error(str(exc))
    elif not args.policy_id.strip() or not args.policy_version.strip():
        pairing.error("policy ID and version must not be blank")
    else:
        try:
            validate_pairing_listener(args.listen, args.device_ip, args.admin_port)
        except ValueError as exc:
            pairing.error(str(exc))
    pepper = os.environ.get("STACKCHAN_SECURITY_PEPPER")
    if not pepper:
        command.error("set STACKCHAN_SECURITY_PEPPER to the existing store's pepper")

    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        tls.load_cert_chain(args.cert, args.key, password=b"")
    except OSError:
        print("error: could not load the TLS certificate and key", file=sys.stderr)
        return 1
    try:
        if args.command == "serve-pairing":
            asyncio.run(_serve_pairing(args.security_db, pepper.encode(), tls, args.port,
                                       args.policy_id, args.policy_version, args.listen, args.device_ip, args.admin_port))
        else:
            asyncio.run(_serve(args.security_db, pepper.encode(), tls, args.port, args.generation,
                               args.listen, args.device_ip))
    except DatabaseError:
        print("error: could not open the existing security database", file=sys.stderr)
        return 1
    except OSError:
        print("error: could not start the TLS listener", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0
