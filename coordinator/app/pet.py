"""寵物狀態模組骨架（Phase 0）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PetState:
    mood: int = 50
    energy: int = 70
    affinity: int = 50
    activity: int = 50
    current_action: str = "idle"

    def clamp(self) -> None:
        for name in ("mood", "energy", "affinity", "activity"):
            value = getattr(self, name)
            setattr(self, name, max(0, min(100, int(value))))
