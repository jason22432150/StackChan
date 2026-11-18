"""
個人版 Bridge CLI（Codex 優先）。

指令：
  stackchan bridge init
  stackchan bridge status
  stackchan bridge pending
  stackchan bridge ingest-hook --adapter codex --file PAYLOAD.json
  stackchan bridge ingest-hook --adapter codex --stdin
  stackchan bridge ingest-hook --adapter codex --argv-json '...'
  stackchan bridge sync --coordinator-url URL --token TOKEN
  stackchan bridge print-codex-setup
  stackchan bridge adapters
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any, Sequence

from stackchan.adapters import AdapterError, get_adapter
from stackchan.bridge.paths import default_bridge_db_path, default_bridge_id
from stackchan.bridge.service import BridgeService, dump_json
from stackchan.bridge.store import BridgeStore, BridgeStoreError
from stackchan.sync import BridgeSyncClient, HttpSyncTransport, SyncTransportError


def build_parser() -> argparse.ArgumentParser:
    """建立 bridge 子命令 parser。"""
    parser = argparse.ArgumentParser(
        prog="stackchan bridge",
        description="StackChan Bridge CLI（本機 Codex Adapter／SQLite Outbox；不直送 CoreS3）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="初始化 Bridge SQLite Outbox")
    _add_common_db(init_p)
    init_p.add_argument("--epoch", default="epoch-1", help="初始 epoch")

    status_p = sub.add_parser("status", help="顯示 pending／sequence 狀態")
    _add_common_db(status_p)

    pending_p = sub.add_parser("pending", help="列出尚未送達 Coordinator 的事件摘要")
    _add_common_db(pending_p)
    pending_p.add_argument("--limit", type=int, default=50, help="最多列出幾筆")

    ingest_p = sub.add_parser(
        "ingest-hook",
        help="讀取 Codex Hook／notify JSON 並寫入 Outbox",
    )
    _add_common_db(ingest_p)
    ingest_p.add_argument(
        "--adapter",
        required=True,
        choices=("codex", "cursor", "codex.hooks", "cursor.hooks"),
        help="受授權 Adapter（首版以 Codex 為主；Cursor 僅預留）",
    )
    source = ingest_p.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="JSON 檔案路徑")
    source.add_argument(
        "--stdin",
        action="store_true",
        help="自 stdin 讀取 JSON（Codex hooks）",
    )
    source.add_argument(
        "--argv-json",
        metavar="JSON",
        help="自命令列參數讀取 JSON（Codex legacy notify）",
    )

    sync_p = sub.add_parser(
        "sync",
        help="將 pending Outbox 上傳至 Pi Coordinator（失敗則保留重試；不直送 CoreS3）",
    )
    _add_common_db(sync_p)
    sync_p.add_argument(
        "--coordinator-url",
        default=os.environ.get("STACKCHAN_COORDINATOR_URL", ""),
        help="Pi Coordinator 根 URL（也可用 STACKCHAN_COORDINATOR_URL）",
    )
    sync_p.add_argument(
        "--token",
        default=os.environ.get("STACKCHAN_BRIDGE_TOKEN", ""),
        help="Bridge Bearer Token（也可用 STACKCHAN_BRIDGE_TOKEN）",
    )
    sync_p.add_argument(
        "--batch-limit",
        type=int,
        default=100,
        help="單次最多上傳事件數（1..100）",
    )
    sync_p.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP 逾時秒數",
    )
    sync_p.add_argument(
        "--ca-file",
        type=Path,
        default=None,
        help="驗證 Pi TLS 用的 CA PEM（建議正式環境使用）",
    )
    sync_p.add_argument(
        "--insecure",
        action="store_true",
        help="略過 TLS 憑證驗證（僅限信任 LAN 除錯；正式環境勿用）",
    )

    setup_p = sub.add_parser(
        "print-codex-setup",
        help="輸出個人版 Codex hooks.json／notify 設定片段（不修改系統檔）",
    )
    _add_common_db(setup_p)
    setup_p.add_argument(
        "--stackchan-bin",
        default="stackchan",
        help="stackchan 可執行檔名稱或絕對路徑",
    )

    caps_p = sub.add_parser("adapters", help="列出受授權 Adapter 能力")
    caps_p.set_defaults(command="adapters")

    return parser


def _add_common_db(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help=f"Bridge SQLite 路徑（預設：{default_bridge_db_path()}）",
    )
    parser.add_argument(
        "--bridge-id",
        default=None,
        help=f"本機 Bridge 識別（預設：{default_bridge_id()}）",
    )


def _resolve_db(args: argparse.Namespace) -> Path:
    return Path(args.db) if args.db is not None else default_bridge_db_path()


def _resolve_bridge_id(args: argparse.Namespace) -> str:
    return args.bridge_id if args.bridge_id else default_bridge_id()


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 進入點；回傳 process exit code。"""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.command == "adapters":
            return _cmd_adapters()
        if args.command == "init":
            return _cmd_init(args)
        if args.command == "status":
            return _cmd_status(args)
        if args.command == "pending":
            return _cmd_pending(args)
        if args.command == "ingest-hook":
            return _cmd_ingest(args)
        if args.command == "sync":
            return _cmd_sync(args)
        if args.command == "print-codex-setup":
            return _cmd_print_codex_setup(args)
        parser.error(f"未知命令: {args.command}")
        return 2
    except (AdapterError, BridgeStoreError, SyncTransportError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _cmd_adapters() -> int:
    # 首版誠實標示：Codex 為正式支援；Cursor 僅預留、未完成驗收
    for name, support in (("codex", "supported"), ("cursor", "deferred")):
        adapter = get_adapter(name)
        cap = adapter.capability
        print(
            dump_json(
                {
                    "name": name,
                    "support": support,
                    "adapter_id": cap.adapter_id,
                    "source_kind": cap.source_kind,
                    "agent_id": cap.agent_id,
                    "capabilities": list(cap.capabilities),
                    "event_semantics": cap.event_semantics,
                    "confidence_baseline": cap.confidence_baseline,
                    "permissions": list(cap.permissions),
                }
            )
        )
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    db = _resolve_db(args)
    bridge_id = _resolve_bridge_id(args)
    db.parent.mkdir(parents=True, exist_ok=True)
    with BridgeStore(db) as store:
        store.ensure_bridge(bridge_id, epoch=args.epoch)
        settings = store.get_settings(bridge_id)
    print(dump_json({"ok": True, "db": str(db), "settings": settings}))
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    db = _resolve_db(args)
    bridge_id = _resolve_bridge_id(args)
    with BridgeStore(db) as store:
        service = BridgeService(store, bridge_id)
        payload = service.status()
        payload["db"] = str(db)
        print(dump_json(payload))
    return 0


def _cmd_pending(args: argparse.Namespace) -> int:
    if args.limit < 1:
        raise ValueError("--limit 必須 >= 1")
    db = _resolve_db(args)
    bridge_id = _resolve_bridge_id(args)
    with BridgeStore(db) as store:
        service = BridgeService(store, bridge_id)
        print(
            dump_json(
                {
                    "ok": True,
                    "db": str(db),
                    "bridge_id": bridge_id,
                    "pending": service.list_pending_summaries(limit=args.limit),
                    "pending_count": service.status()["pending_count"],
                }
            )
        )
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    url = (args.coordinator_url or "").strip()
    token = (args.token or "").strip()
    if not url:
        raise ValueError("必須提供 --coordinator-url 或 STACKCHAN_COORDINATOR_URL")
    if not token:
        raise ValueError("必須提供 --token 或 STACKCHAN_BRIDGE_TOKEN")
    if not 1 <= args.batch_limit <= 100:
        raise ValueError("--batch-limit 必須在 1..100")
    if args.timeout <= 0:
        raise ValueError("--timeout 必須 > 0")

    db = _resolve_db(args)
    bridge_id = _resolve_bridge_id(args)
    transport = HttpSyncTransport(
        base_url=url,
        timeout_seconds=args.timeout,
        ca_file=args.ca_file,
        insecure_skip_verify=bool(args.insecure),
    )
    with BridgeStore(db) as store:
        client = BridgeSyncClient(
            store,
            bridge_id=bridge_id,
            transport=transport,
            authorization_header=f"Bearer {token}",
            batch_limit=args.batch_limit,
        )
        result = client.sync_once()

    payload: dict[str, Any] = {
        "ok": result.error is None,
        "attempted": result.attempted,
        "uploaded_event_ids": result.uploaded_event_ids,
        "pending_remaining": result.pending_remaining,
        "contiguous_acked_sequence": result.contiguous_acked_sequence,
        "error": result.error,
        "db": str(db),
        "bridge_id": bridge_id,
        "coordinator_url": url,
        "delivers_to_cores3": False,
    }
    if result.ack is not None:
        payload["ack"] = result.ack.to_dict()
    print(dump_json(payload))
    return 0 if result.error is None else 1


def _cmd_ingest(args: argparse.Namespace) -> int:
    raw = _load_payload(args)
    adapter = get_adapter(args.adapter)
    db = _resolve_db(args)
    bridge_id = _resolve_bridge_id(args)
    db.parent.mkdir(parents=True, exist_ok=True)
    with BridgeStore(db) as store:
        service = BridgeService(store, bridge_id)
        outcome = service.ingest_raw(adapter, raw)

    if outcome.skipped:
        print(
            dump_json(
                {
                    "ok": True,
                    "skipped": True,
                    "reason": outcome.reason,
                }
            )
        )
        return 0

    assert outcome.result is not None
    print(
        dump_json(
            {
                "ok": True,
                "skipped": False,
                "created": outcome.result.created,
                "event_id": outcome.result.event_id,
                "observation_id": outcome.result.observation_id,
                "bridge_sequence": outcome.result.bridge_sequence,
                "epoch": outcome.result.epoch,
                "event_type": (outcome.event or {}).get("event_type"),
                "evidence_level": (outcome.event or {}).get("evidence_level"),
                "db": str(db),
            }
        )
    )
    return 0


def _cmd_print_codex_setup(args: argparse.Namespace) -> int:
    """產生可複製的 Codex 設定；不寫入 ~/.codex。"""
    db = _resolve_db(args).resolve()
    bridge_id = _resolve_bridge_id(args)
    binary = args.stackchan_bin
    hook_cmd = (
        f"{shlex.quote(binary)} bridge ingest-hook "
        f"--db {shlex.quote(str(db))} --bridge-id {shlex.quote(bridge_id)} "
        f"--adapter codex --stdin"
    )
    notify_cmd = [
        binary,
        "bridge",
        "ingest-hook",
        "--db",
        str(db),
        "--bridge-id",
        bridge_id,
        "--adapter",
        "codex",
        "--argv-json",
    ]
    hooks_json = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": hook_cmd,
                            "timeout": 30,
                        }
                    ]
                }
            ],
            "PermissionRequest": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": hook_cmd,
                            "timeout": 30,
                        }
                    ]
                }
            ],
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": hook_cmd,
                            "timeout": 30,
                        }
                    ]
                }
            ],
        }
    }
    wrapper = Path(__file__).resolve().parents[3] / "deploy" / "bridge" / "codex-notify.sh"
    print(
        dump_json(
            {
                "ok": True,
                "notes": [
                    "此命令只輸出設定片段，不會修改 ~/.codex。",
                    "請先執行 stackchan bridge init，再把 hooks／notify 貼到 Codex 設定。",
                    "Codex 可能要求在 /hooks 中信任新 hook。",
                    "response.completed 不等於 task.succeeded。",
                    "Bridge 只寫本機 Outbox；尚未連線 Pi Coordinator（下一項功能）。",
                    "絕不可讓 Bridge 直送 CoreS3。",
                ],
                "db": str(db),
                "bridge_id": bridge_id,
                "hooks_json": hooks_json,
                "hooks_file_hint": "~/.codex/hooks.json 或專案 .codex/hooks.json",
                "notify": {
                    "description": "legacy notify：JSON 在最後一個 argv，請使用 wrapper",
                    "config_toml_example": (
                        f"notify = [{shlex.quote(str(wrapper))}]"
                        if wrapper.exists()
                        else 'notify = ["/absolute/path/to/deploy/bridge/codex-notify.sh"]'
                    ),
                    "wrapper": str(wrapper),
                    "env": {
                        "STACKCHAN_BRIDGE_DB": str(db),
                        "STACKCHAN_BRIDGE_ID": bridge_id,
                        "STACKCHAN_BIN": binary,
                    },
                    "direct_argv_prefix": notify_cmd,
                },
            }
        )
    )
    return 0


def _load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.file is not None:
        text = Path(args.file).read_text(encoding="utf-8")
        data = json.loads(text)
    elif args.stdin:
        text = sys.stdin.read()
        data = json.loads(text)
    else:
        data = json.loads(args.argv_json)

    if not isinstance(data, dict):
        raise ValueError("Hook payload 必須為 JSON object")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
