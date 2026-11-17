"""人工確認配對流程：start → confirm → complete。"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any

from stackchan.contracts import validate_pairing_message
from stackchan.contracts.authz import Principal
from stackchan.security.identity import issue_opaque_token
from stackchan.security.policy import PolicyError, PolicyService
from stackchan.security.store import SecurityStore

_DEFAULT_SCOPES = {
    "bridge": ["bridge:write", "bridge:sync"],
    "device": ["device:policy", "device:receipt", "device:stream"],
    "dashboard": ["dashboard:read", "read:write"],
}


class PairingError(ValueError):
    """配對流程錯誤。"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _fmt(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _user_code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class PairingService:
    """Coordinator 配對服務（契約對齊 pairing.schema.json）。"""

    def __init__(self, store: SecurityStore) -> None:
        self._store = store

    def start(self, request: dict[str, Any]) -> dict[str, Any]:
        validated = validate_pairing_message("PairingStartRequest", request)
        pairing_id = f"pair_{secrets.token_hex(8)}"
        user_code = _user_code()
        expires_at = _fmt(_utc_now() + timedelta(minutes=10))
        self._store.create_pairing_session(
            pairing_id=pairing_id,
            subject_type=validated["subject_type"],
            display_name=validated["display_name"],
            user_code=user_code,
            expires_at=expires_at,
        )
        challenge = {
            "schema_version": "0.1",
            "pairing_id": pairing_id,
            "subject_type": validated["subject_type"],
            "user_code": user_code,
            "expires_at": expires_at,
        }
        return validate_pairing_message("PairingChallenge", challenge)

    def confirm(self, request: dict[str, Any], *, admin: Principal) -> dict[str, Any]:
        if "admin:pairing" not in admin.scopes or admin.revoked:
            raise PairingError("需要 admin:pairing 且未撤銷的管理員")
        validated = validate_pairing_message("PairingConfirmRequest", request)
        session = self._store.get_pairing(validated["pairing_id"])
        if session is None:
            raise PairingError("未知 pairing_id")
        if session["status"] != "pending":
            raise PairingError(f"配對狀態不可確認: {session['status']}")
        if session["expires_at"] <= _fmt(_utc_now()):
            self._store.set_pairing_status(validated["pairing_id"], "expired")
            raise PairingError("配對已過期")
        if not self._store.verify_pairing_code(validated["pairing_id"], validated["user_code"]):
            raise PairingError("user_code 不正確")
        if not validated["approved"]:
            self._store.set_pairing_status(validated["pairing_id"], "rejected")
            return {
                "schema_version": "0.1",
                "error": "forbidden",
                "message": "配對已被拒絕",
                "retryable": False,
            }
        self._store.set_pairing_status(validated["pairing_id"], "approved")
        return {
            "schema_version": "0.1",
            "error": "unauthorized",
            "message": "配對已核准，請呼叫 complete 取得短期憑證",
            "retryable": False,
        }

    def complete(self, pairing_id: str, *, device_policy: tuple[str, str] | None = None) -> dict[str, Any]:
        with self._store.write_transaction():
            session = self._store.get_pairing(pairing_id)
            if session is None:
                raise PairingError("未知 pairing_id")
            if session["status"] != "approved":
                raise PairingError("僅核准後的配對可 complete")
            if session["expires_at"] > _fmt(_utc_now()):
                return self._complete_approved(pairing_id, session, device_policy)
            self._store.set_pairing_status(pairing_id, "expired")
        raise PairingError("配對已過期")

    def _complete_approved(
        self, pairing_id: str, session: dict[str, Any], device_policy: tuple[str, str] | None,
    ) -> dict[str, Any]:
        subject_type = session["subject_type"]
        if device_policy is not None and subject_type != "device":
            raise PairingError("裝置政策僅適用於裝置配對")
        subject_id = f"{subject_type}_{secrets.token_hex(6)}"
        scopes = list(_DEFAULT_SCOPES.get(subject_type, ["dashboard:read"]))
        token = issue_opaque_token()
        expires_at = _fmt(_utc_now() + timedelta(hours=12))
        grant_id = f"grant_{secrets.token_hex(8)}"

        self._store.upsert_subject(subject_id, subject_type, session["display_name"])
        if device_policy is not None:
            policies = PolicyService(self._store)
            try:
                policies.bind_device(subject_id, *device_policy)
                policies.issue_device_lease(subject_id)
            except PolicyError as exc:
                raise PairingError("配對政策無效") from exc
        self._store.issue_grant(
            grant_id=grant_id,
            subject_id=subject_id,
            subject_type=subject_type,
            token_plaintext=token,
            scopes=scopes,
            expires_at=expires_at,
        )
        self._store.set_pairing_status(pairing_id, "completed", subject_id=subject_id)

        response = {
            "schema_version": "0.1",
            "pairing_id": pairing_id,
            "subject_id": subject_id,
            "subject_type": subject_type,
            "access_token": token,
            "scopes": scopes,
            "token_expires_at": expires_at,
        }
        return validate_pairing_message("PairingCompleteResponse", response)
