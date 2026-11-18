"""個人版 Bridge 本機路徑預設值。"""

from __future__ import annotations

import os
from pathlib import Path


def default_bridge_db_path() -> Path:
    """
    預設 Outbox SQLite 路徑。

    優先順序：
    1. STACKCHAN_BRIDGE_DB
    2. ~/.stackchan/bridge.sqlite3
    """
    override = os.environ.get("STACKCHAN_BRIDGE_DB")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".stackchan" / "bridge.sqlite3"


def default_bridge_id() -> str:
    """預設 Bridge ID（可用 STACKCHAN_BRIDGE_ID 覆寫）。"""
    return os.environ.get("STACKCHAN_BRIDGE_ID", "bridge_primary")
