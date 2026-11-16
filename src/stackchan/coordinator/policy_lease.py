"""裝置政策租約交換（P2-04）：GET /v1/devices/{deviceId}/policy。

尚未部署真實 HTTP listener；以 ApiGate＋PolicyService 驗證授權與 Fail-Closed。
回傳快照可供 CoreS3 在連線 device-stream 前綁定 policy_version／expires_utc_ms。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from stackchan.contracts.authz import ApiGate, AuthorizationError, Principal
from stackchan.security.policy import PolicyError, PolicyService

_PRIVACY_MODES = frozenset({"private", "public", "strict"})
_MAX_DEVICE_ID_BYTES = 128


@dataclass(frozen=True, slots=True)
class PolicyLease:
    """裝置可用的政策租約快照（成功路徑不含 revoked）。"""

    policy_id: str
    version: str
    privacy_mode: str
    valid_until: str
    expires_utc_ms: int

    def as_openapi_policy(self) -> dict[str, Any]:
        """對齊 OpenAPI Policy schema（不含內部 expires_utc_ms）。"""
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "privacy_mode": self.privacy_mode,
            "valid_until": self.valid_until,
        }


def _utc_milliseconds(value: str) -> int:
    """將 ISO-8601 UTC 轉成毫秒；拒絕無時區或非有限結果。"""
    parsed = datetime.fromisoformat(value.upper())
    if parsed.tzinfo is None:
        raise PolicyError("policy_time_invalid")
    millis = int(parsed.astimezone(timezone.utc).timestamp() * 1000)
    if millis <= 0:
        raise PolicyError("policy_time_invalid")
    return millis


def _assert_device_principal(principal: Principal | None, device_id: str) -> Principal:
    if principal is None:
        raise AuthorizationError(
            "unauthorized",
            "政策租約不可匿名",
            http_status=401,
        )
    if principal.subject_type != "device" or principal.subject_id != device_id:
        raise AuthorizationError(
            "forbidden",
            f"憑證不可讀取裝置 {device_id} 的政策",
            http_status=403,
        )
    return principal


class DevicePolicyLeaseService:
    """授權後發放目前有效政策租約；過期／撤銷／錯裝置一律 Fail-Closed。"""

    def __init__(self, gate: ApiGate, policies: PolicyService) -> None:
        self._gate = gate
        self._policies = policies

    def get_device_policy(
        self,
        device_id: str,
        *,
        authorization_header: str | None,
        now: str | None = None,
    ) -> PolicyLease:
        """
        GET /v1/devices/{deviceId}/policy

        僅允許同一 device subject 且具備 device:policy 的憑證讀取。
        """
        if (
            not device_id
            or len(device_id) > _MAX_DEVICE_ID_BYTES
            or not device_id.isascii()
            or not device_id.isprintable()
            or any(ch.isspace() for ch in device_id)
        ):
            raise AuthorizationError(
                "forbidden",
                "無效 device_id",
                http_status=403,
            )

        path = f"/v1/devices/{device_id}/policy"
        principal = self._gate.authorize("GET", path, authorization_header)
        _assert_device_principal(principal, device_id)

        try:
            snapshot = self._policies.issue_device_lease(device_id, now=now)
            expires_utc_ms = _utc_milliseconds(snapshot["valid_until"])
            if snapshot["privacy_mode"] not in _PRIVACY_MODES:
                raise PolicyError("policy_privacy_invalid")
            if now is not None and expires_utc_ms <= _utc_milliseconds(now):
                raise PolicyError("policy_expired")
        except PolicyError as exc:
            raise AuthorizationError(
                "forbidden",
                f"政策租約不可用: {exc}",
                http_status=403,
            ) from exc

        return PolicyLease(
            policy_id=snapshot["policy_id"],
            version=snapshot["version"],
            privacy_mode=snapshot["privacy_mode"],
            valid_until=snapshot["valid_until"],
            expires_utc_ms=expires_utc_ms,
        )
