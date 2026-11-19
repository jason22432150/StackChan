"""
個人版裝置 CLI。

指令：
  stackchan device pull-pending ...
  stackchan device accept-boot      # Device Token + 啟動設定驗收
  stackchan device provision-nvs    # 產出 personal_pend NVS CSV／bin（不燒錄）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from stackchan.device.boot_config import BootConfigError, PersonalPendingBootConfig
from stackchan.device.nvs_provision import NvsProvisionError, write_personal_pending_nvs_provision
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

    accept = sub.add_parser(
        "accept-boot",
        help="驗收 Device Token（live pull）並輸出個人版啟動接線摘要（不燒錄）",
    )
    accept.add_argument(
        "--coordinator-url",
        default=os.environ.get("STACKCHAN_COORDINATOR_URL", ""),
        help="覆寫 STACKCHAN_COORDINATOR_URL",
    )
    accept.add_argument("--limit", type=int, default=5, help="驗收 pull 的 limit")
    accept.add_argument("--timeout", type=float, default=10.0)
    accept.add_argument("--ca-file", type=Path, default=None)
    accept.add_argument("--insecure", action="store_true")

    prov = sub.add_parser(
        "provision-nvs",
        help="產出 personal_pend NVS CSV／可選 bin（不燒錄、不寫 eFuse）",
    )
    prov.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="輸出目錄（將寫入 CSV／README；含 token，勿提交）",
    )
    prov.add_argument(
        "--coordinator-url",
        default=os.environ.get("STACKCHAN_COORDINATOR_URL", ""),
        help="覆寫 STACKCHAN_COORDINATOR_URL",
    )
    prov.add_argument(
        "--size",
        default="0x4000",
        help="NVS partition 大小（hex 或十進位，預設 0x4000）",
    )
    prov.add_argument(
        "--no-bin",
        action="store_true",
        help="只產 CSV，不呼叫 nvs_partition_gen",
    )
    prov.add_argument(
        "--check-token",
        action="store_true",
        help="產物前先對 Pi 做一次 pull 驗收 Device Token",
    )
    prov.add_argument("--timeout", type=float, default=10.0)
    prov.add_argument("--ca-file", type=Path, default=None)
    prov.add_argument("--insecure", action="store_true")
    prov.add_argument(
        "--flash",
        action="store_true",
        help="拒絕：本 CLI 不燒錄；需另行核准後手動 esptool",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "pull-pending":
            return _cmd_pull_pending(args)
        if args.command == "accept-boot":
            return _cmd_accept_boot(args)
        if args.command == "provision-nvs":
            return _cmd_provision_nvs(args)
        parser.error(f"未知命令: {args.command}")
        return 2
    except (BootConfigError, DevicePullError, NvsProvisionError, OSError, ValueError) as exc:
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


def _cmd_accept_boot(args: argparse.Namespace) -> int:
    env = dict(os.environ)
    if (args.coordinator_url or "").strip():
        env["STACKCHAN_COORDINATOR_URL"] = args.coordinator_url.strip()
    boot = PersonalPendingBootConfig.from_env(env)
    pull_url = (args.coordinator_url or "").strip() or boot.coordinator_base_url()
    client = DevicePullClient(
        base_url=pull_url,
        device_id=boot.device_id,
        device_token=boot.device_token,
        timeout_seconds=args.timeout,
        ca_file=args.ca_file,
        insecure_skip_verify=bool(args.insecure),
    )
    result = client.pull_pending(limit=args.limit)
    payload: dict[str, Any] = {
        "ok": True,
        "device_token_accepted": True,
        "pull": {
            "device_id": result.device_id,
            "count": len(result.items),
            "ok": result.ok,
        },
        "boot": boot.to_public_dict(),
        "firmware_hook": "trySchedulePersonalPendingBootAfterSntp",
        "nvs_namespace": "personal_pend",
        "note": "host 驗收通過；裝置需加密 NVS 寫入 personal_pend 後開機才會自動排程",
        "flashed": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _parse_size(raw: str) -> int:
    text = (raw or "").strip().lower()
    if not text:
        raise ValueError("--size 不可為空")
    return int(text, 0)


def _cmd_provision_nvs(args: argparse.Namespace) -> int:
    if bool(args.flash):
        raise NvsProvisionError(
            "拒絕 --flash：本 CLI 只產 NVS 產物，不燒錄、不寫 eFuse。"
            "請在明確核准後手動使用 esptool（見輸出 README）。"
        )
    env = dict(os.environ)
    if (args.coordinator_url or "").strip():
        env["STACKCHAN_COORDINATOR_URL"] = args.coordinator_url.strip()
    boot = PersonalPendingBootConfig.from_env(env)
    size = _parse_size(args.size)

    token_check: dict[str, Any] | None = None
    if bool(args.check_token):
        pull_url = (args.coordinator_url or "").strip() or boot.coordinator_base_url()
        client = DevicePullClient(
            base_url=pull_url,
            device_id=boot.device_id,
            device_token=boot.device_token,
            timeout_seconds=args.timeout,
            ca_file=args.ca_file,
            insecure_skip_verify=bool(args.insecure),
        )
        result = client.pull_pending(limit=1)
        token_check = {
            "ok": result.ok,
            "device_id": result.device_id,
            "count": len(result.items),
        }

    artifacts = write_personal_pending_nvs_provision(
        boot,
        args.out_dir,
        partition_size=size,
        generate_bin=not bool(args.no_bin),
    )
    payload: dict[str, Any] = {
        "ok": True,
        "flashed": False,
        "efuse_written": False,
        "out_dir": str(artifacts.out_dir),
        "csv": str(artifacts.csv_path),
        "bin": str(artifacts.bin_path) if artifacts.bin_path else None,
        "readme": str(artifacts.readme_path),
        "boot": {k: v for k, v in artifacts.public_summary.items() if k != "device_token"},
        "token_check": token_check,
        "note": "產物含 Device Token；勿提交 git。寫入裝置需你核准後手動執行。",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
