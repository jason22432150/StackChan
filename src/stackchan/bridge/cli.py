"""
Windows Bridge CLI（P2-01）。

指令：
  stackchan bridge init --db PATH --bridge-id ID
  stackchan bridge status --db PATH --bridge-id ID
  stackchan bridge ingest-hook --adapter codex|cursor --file PAYLOAD.json
  stackchan bridge ingest-hook --adapter codex --stdin   # 或 argv JSON（Codex notify）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from stackchan.adapters import AdapterError, get_adapter
from stackchan.bridge.service import BridgeService, dump_json
from stackchan.bridge.store import BridgeStore, BridgeStoreError


def build_parser() -> argparse.ArgumentParser:
    """建立 bridge 子命令 parser。"""
    parser = argparse.ArgumentParser(
        prog="stackchan bridge",
        description="StackChan Windows Bridge CLI（本機 Adapter／Outbox）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="初始化 Bridge SQLite")
    _add_common_db(init_p)
    init_p.add_argument("--epoch", default="epoch-1", help="初始 epoch")

    status_p = sub.add_parser("status", help="顯示 pending／sequence 狀態")
    _add_common_db(status_p)

    ingest_p = sub.add_parser(
        "ingest-hook",
        help="讀取 Codex／Cursor Hook JSON 並寫入 Outbox",
    )
    _add_common_db(ingest_p)
    ingest_p.add_argument(
        "--adapter",
        required=True,
        choices=("codex", "cursor", "codex.hooks", "cursor.hooks"),
        help="受授權 Adapter",
    )
    source = ingest_p.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="JSON 檔案路徑")
    source.add_argument(
        "--stdin",
        action="store_true",
        help="自 stdin 讀取 JSON（Cursor／Codex hooks）",
    )
    source.add_argument(
        "--argv-json",
        metavar="JSON",
        help="自命令列參數讀取 JSON（Codex legacy notify）",
    )

    caps_p = sub.add_parser("adapters", help="列出受授權 Adapter 能力")
    caps_p.set_defaults(command="adapters")

    return parser


def _add_common_db(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="Bridge SQLite 路徑",
    )
    parser.add_argument(
        "--bridge-id",
        required=True,
        help="本機 Bridge 識別",
    )


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
        if args.command == "ingest-hook":
            return _cmd_ingest(args)
        parser.error(f"未知命令: {args.command}")
        return 2
    except (AdapterError, BridgeStoreError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _cmd_adapters() -> int:
    for name in ("codex", "cursor"):
        adapter = get_adapter(name)
        cap = adapter.capability
        print(
            dump_json(
                {
                    "name": name,
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
    with BridgeStore(args.db) as store:
        store.ensure_bridge(args.bridge_id, epoch=args.epoch)
        settings = store.get_settings(args.bridge_id)
    print(dump_json({"ok": True, "settings": settings}))
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    with BridgeStore(args.db) as store:
        service = BridgeService(store, args.bridge_id)
        print(dump_json(service.status()))
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    raw = _load_payload(args)
    adapter = get_adapter(args.adapter)
    with BridgeStore(args.db) as store:
        service = BridgeService(store, args.bridge_id)
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
