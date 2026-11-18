"""定位凍結契約目錄（單一來源：docs/stackchan-agent-spec/contracts）。"""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """由套件位置向上尋找含契約目錄的 repository root。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "docs" / "stackchan-agent-spec" / "contracts"
        if candidate.is_dir() and (candidate / "agent-event.schema.json").is_file():
            return parent
    raise FileNotFoundError(
        "找不到 docs/stackchan-agent-spec/contracts；請在 repository root 執行測試"
    )


def contracts_dir() -> Path:
    """回傳凍結 JSON Schema 目錄（可用 STACKCHAN_CONTRACTS_DIR 覆寫，供容器使用）。"""
    override = os.environ.get("STACKCHAN_CONTRACTS_DIR")
    if override:
        path = Path(override)
        if not (path.is_dir() and (path / "agent-event.schema.json").is_file()):
            raise FileNotFoundError(f"STACKCHAN_CONTRACTS_DIR 無效：{path}")
        return path
    return repo_root() / "docs" / "stackchan-agent-spec" / "contracts"
