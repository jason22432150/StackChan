"""StackChan host-side package（契約／後續 Bridge・Coordinator）。"""

from __future__ import annotations


def main() -> None:
    """CLI 佔位；Phase 1 以契約與儲存庫測試為主。"""
    from stackchan.contracts import CONTRACT_SCHEMA_VERSION

    print(f"stackchan contracts schema_version={CONTRACT_SCHEMA_VERSION}")
