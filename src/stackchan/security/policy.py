"""政策版號驗證與撤銷（Fail-Closed）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from stackchan.security.store import SecurityStore


class PolicyError(ValueError):
    """政策驗證失敗。"""


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """裝置政策檢查結果。"""

    allowed: bool
    reason: str
    policy_id: str | None = None
    policy_version: str | None = None


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class PolicyService:
    """隱私政策發佈／撤銷／裝置綁定驗證。"""

    def __init__(self, store: SecurityStore) -> None:
        self._store = store

    def publish(self, policy: dict[str, Any]) -> None:
        required = {"policy_id", "version", "privacy_mode", "valid_until"}
        missing = required - set(policy)
        if missing:
            raise PolicyError(f"缺少欄位: {sorted(missing)}")
        self._store.publish_policy(
            policy_id=policy["policy_id"],
            version=policy["version"],
            privacy_mode=policy["privacy_mode"],
            valid_until=policy["valid_until"],
        )

    def revoke(self, policy_id: str, version: str) -> None:
        existing = self._store.get_policy(policy_id, version)
        if existing is None:
            raise PolicyError("未知政策版本")
        self._store.revoke_policy(policy_id, version)

    def bind_device(self, device_id: str, policy_id: str, policy_version: str) -> None:
        existing = self._store.get_policy(policy_id, policy_version)
        if existing is None:
            raise PolicyError("無法綁定未知政策")
        if int(existing["revoked"]) == 1:
            raise PolicyError("不可綁定已撤銷政策")
        self._store.bind_device_policy(device_id, policy_id, policy_version)

    def validate_device_presentation(
        self,
        device_id: str,
        *,
        claimed_policy_version: str | None,
        now: str | None = None,
    ) -> PolicyDecision:
        """
        Fail-Closed：缺綁定／版號不符／撤銷／過期 => 禁止 Agent 通知呈現。
        """
        current = now or _utc_now_str()
        binding = self._store.get_device_binding(device_id)
        if binding is None:
            return PolicyDecision(False, "device_unbound")
        policy = self._store.get_policy(binding["policy_id"], binding["policy_version"])
        if policy is None:
            return PolicyDecision(False, "policy_missing")
        if int(policy["revoked"]) == 1:
            return PolicyDecision(
                False,
                "policy_revoked",
                policy_id=policy["policy_id"],
                policy_version=policy["version"],
            )
        if policy["valid_until"] <= current:
            return PolicyDecision(
                False,
                "policy_expired",
                policy_id=policy["policy_id"],
                policy_version=policy["version"],
            )
        if claimed_policy_version is None:
            return PolicyDecision(False, "policy_version_missing")
        if claimed_policy_version != policy["version"]:
            return PolicyDecision(
                False,
                "policy_version_mismatch",
                policy_id=policy["policy_id"],
                policy_version=policy["version"],
            )
        return PolicyDecision(
            True,
            "ok",
            policy_id=policy["policy_id"],
            policy_version=policy["version"],
        )
