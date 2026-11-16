"""StackChan host-side package（契約／Bridge／Coordinator／Security）。"""

from __future__ import annotations

import sys
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> None:
    """
    頂層 CLI。

    用法：
      stackchan bridge ...
      stackchan version
    """
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args or args[0] in {"-h", "--help", "help"}:
        print("usage: stackchan <bridge|version> ...")
        print("  bridge   Windows Bridge CLI（init／status／ingest-hook／adapters）")
        print("  version  顯示契約 schema_version")
        raise SystemExit(0 if args else 2)

    command, rest = args[0], args[1:]
    if command == "version":
        from stackchan.contracts import CONTRACT_SCHEMA_VERSION

        print(f"stackchan contracts schema_version={CONTRACT_SCHEMA_VERSION}")
        return

    if command == "bridge":
        from stackchan.bridge.cli import main as bridge_main

        raise SystemExit(bridge_main(rest))

    print(f"error: 未知命令 {command!r}", file=sys.stderr)
    raise SystemExit(2)
