"""Bridge 本機儲存與 Outbox（P1-03）。"""

from stackchan.bridge.store import (
    BridgeStore,
    BridgeStoreError,
    IngestResult,
)

__all__ = [
    "BridgeStore",
    "BridgeStoreError",
    "IngestResult",
]
