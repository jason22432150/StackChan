"""定位凍結契約目錄（單一來源：docs/stackchan-agent-spec/contracts）。"""

from __future__ import annotations

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
    """回傳凍結 JSON Schema 目錄。"""
    return repo_root() / "docs" / "stackchan-agent-spec" / "contracts"
