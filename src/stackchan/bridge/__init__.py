"""Bridge 本機儲存、服務與 CLI（P1-03／P2-01）。"""

from stackchan.bridge.service import BridgeIngestOutcome, BridgeService
from stackchan.bridge.store import (
    BridgeStore,
    BridgeStoreError,
    IngestResult,
)

__all__ = [
    "BridgeIngestOutcome",
    "BridgeService",
    "BridgeStore",
    "BridgeStoreError",
    "IngestResult",
]
