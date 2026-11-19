"""
個人版裝置 CLI。

指令：
  stackchan device pull-pending --coordinator-url URL --device-id ID --token TOKEN
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from stackchan.device.pull_client import DevicePullClient, DevicePullError


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stackchan device")
    sub = parser.add_subparsers(dest="command", required=True)

    pull = sub.add_parser(
        "pull-pending",
        help="自 Pi Coordinator 拉取此裝置的 pending 通知摘要（不燒錄、不直送 CoreS3 UI）",
    )
    pull.add_argument(
        "--coordinator-url",
        default=os.environ.get("STACKCHAN_COORDINATOR_URL", ""),
        help="Pi Coordinator 根 URL（也可用 STACKCHAN_COORDINATOR_URL）",
    )
    pull.add_argument(
        "--device-id",
        default=os.environ.get("STACKCHAN_DEVICE_ID", "cores3_primary"),
        help="裝置 ID（也可用 STACKCHAN_DEVICE_ID）",
    )
    pull.add_argument(
        "--token",
        default=os.environ.get("STACKCHAN_DEVICE_TOKEN", ""),
        help="Device Bearer Token（也可用 STACKCHAN_DEVICE_TOKEN）",
    )
    pull.add_argument("--limit", type=int, default=50, help="最多筆數（1..100）")
    pull.add_argument("--timeout", type=float, default=10.0, help="HTTP 逾時秒數")
    pull.add_argument("--ca-file", type=Path, default=None, help="驗證 Pi TLS 的 CA PEM")
    pull.add_argument(
        "--insecure",
        action="store_true",
        help="略過 TLS 驗證（僅限信任 LAN 除錯）",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "pull-pending":
            return _cmd_pull_pending(args)
        parser.error(f"未知命令: {args.command}")
        return 2
    except (DevicePullError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _cmd_pull_pending(args: argparse.Namespace) -> int:
    url = (args.coordinator_url or "").strip()
    token = (args.token or "").strip()
    device_id = (args.device_id or "").strip()
    if not url:
        raise ValueError("必須提供 --coordinator-url 或 STACKCHAN_COORDINATOR_URL")
    if not token:
        raise ValueError("必須提供 --token 或 STACKCHAN_DEVICE_TOKEN")
    if not device_id:
        raise ValueError("必須提供 --device-id 或 STACKCHAN_DEVICE_ID")
    if not 1 <= args.limit <= 100:
        raise ValueError("--limit 必須在 1..100")
    if args.timeout <= 0:
        raise ValueError("--timeout 必須 > 0")

    client = DevicePullClient(
        base_url=url,
        device_id=device_id,
        device_token=token,
        timeout_seconds=args.timeout,
        ca_file=args.ca_file,
        insecure_skip_verify=bool(args.insecure),
    )
    result = client.pull_pending(limit=args.limit)
    payload: dict[str, Any] = {
        "ok": result.ok,
        "device_id": result.device_id,
        "count": len(result.items),
        "items": result.items,
        "delivers_to_cores3_ui": False,
        "error": result.error,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
