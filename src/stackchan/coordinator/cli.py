"""Launch the CoreS3 bench listener on loopback."""

from __future__ import annotations

import argparse
import asyncio
import os
import ssl
import sys
from pathlib import Path
from sqlite3 import Error as DatabaseError
from typing import Sequence

from stackchan.contracts.authz import ApiGate
from stackchan.coordinator.device_stream_server import serve_device_stream
from stackchan.coordinator.mvp_dispatcher import create_mvp_notification_dispatcher
from stackchan.coordinator.policy_lease import DevicePolicyLeaseService
from stackchan.coordinator.runtime_limits import CORE_S3_MVP_RUNTIME_LIMITS
from stackchan.security.auth_bridge import StoreBackedTokenDirectory
from stackchan.security.identity import TokenHasher
from stackchan.security.policy import PolicyService
from stackchan.security.store import SecurityStore


async def _serve(
    db: Path, pepper: bytes, tls: ssl.SSLContext, port: int, generation: int,
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
        ) as server:
            host, bound_port = server.sockets[0].getsockname()
            print(f"Coordinator ready on {host}:{bound_port} (TLS, generation={generation})", flush=True)
            await server.serve_forever()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stackchan coordinator")
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve = subcommands.add_parser("serve-device", help="serve CoreS3 policy and stream on one loopback TLS port")
    serve.add_argument("--security-db", required=True, type=Path, help="existing SecurityStore SQLite file")
    serve.add_argument("--cert", required=True, type=Path, help="TLS server certificate chain in PEM format")
    serve.add_argument("--key", required=True, type=Path, help="TLS server private key file")
    serve.add_argument("--port", required=True, type=int, help="loopback port (0 selects a temporary port)")
    serve.add_argument("--generation", required=True, type=int, help="CoreS3 Coordinator generation")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        serve.error("--port must be between 0 and 65535")
    if not 0 <= args.generation < (1 << 64):
        serve.error("--generation must be a uint64")
    pepper = os.environ.get("STACKCHAN_SECURITY_PEPPER")
    if not pepper:
        serve.error("set STACKCHAN_SECURITY_PEPPER to the existing store's pepper")

    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        tls.load_cert_chain(args.cert, args.key, password=b"")
    except OSError:
        print("error: could not load the TLS certificate and key", file=sys.stderr)
        return 1
    try:
        asyncio.run(_serve(args.security_db, pepper.encode(), tls, args.port, args.generation))
    except DatabaseError:
        print("error: could not open the existing security database", file=sys.stderr)
        return 1
    except OSError:
        print("error: could not start the loopback TLS listener", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0
