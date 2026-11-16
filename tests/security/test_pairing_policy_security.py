"""P1-05 分層身份、配對、政策撤銷與密鑰保護測試。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from stackchan.contracts import ApiGate, Principal
from stackchan.security import (
    DEFAULT_BIND_HOST,
    PairingError,
    PairingService,
    PolicyService,
    SecurityStore,
    StoreBackedTokenDirectory,
    assert_safe_bind_host,
    redact_secrets,
)
from stackchan.security.exposure import ExposureError


def _future(hours: int = 24) -> str:
    return (
        datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=hours)
    ).isoformat().replace("+00:00", "Z")


def _past() -> str:
    return (
        datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
    ).isoformat().replace("+00:00", "Z")


def test_pairing_flow_issues_hashed_grant_only(
    pairing: PairingService, security_db: SecurityStore
) -> None:
    challenge = pairing.start(
        {
            "schema_version": "0.1",
            "subject_type": "device",
            "display_name": "CoreS3 Desk",
            "client_public_key": None,
        }
    )
    admin = Principal("admin_1", "admin", frozenset({"admin:pairing"}))
    pairing.confirm(
        {
            "schema_version": "0.1",
            "pairing_id": challenge["pairing_id"],
            "user_code": challenge["user_code"],
            "approved": True,
        },
        admin=admin,
    )
    complete = pairing.complete(challenge["pairing_id"])
    token = complete["access_token"]
    assert len(token) >= 16

    # DB 不得有明文 token 欄位；且 token 字串不得出現在 grants 列
    assert security_db.count_plaintext_token_columns() == 0
    blob = security_db._conn.execute(
        "SELECT token_hash, scopes_json FROM authorization_grants"
    ).fetchone()
    assert token not in blob["token_hash"]
    assert token not in blob["scopes_json"]

    principal = security_db.resolve_principal(token)
    assert principal is not None
    assert principal.subject_type == "device"
    assert "device:stream" in principal.scopes


def test_pairing_rejects_wrong_code_and_incomplete(
    pairing: PairingService,
) -> None:
    challenge = pairing.start(
        {
            "schema_version": "0.1",
            "subject_type": "bridge",
            "display_name": "Win Bridge",
        }
    )
    admin = Principal("admin_1", "admin", frozenset({"admin:pairing"}))
    with pytest.raises(PairingError):
        pairing.confirm(
            {
                "schema_version": "0.1",
                "pairing_id": challenge["pairing_id"],
                "user_code": "XXXXXX",
                "approved": True,
            },
            admin=admin,
        )
    with pytest.raises(PairingError):
        pairing.complete(challenge["pairing_id"])


def test_revoked_token_forbidden_by_api_gate(
    pairing: PairingService, security_db: SecurityStore
) -> None:
    challenge = pairing.start(
        {
            "schema_version": "0.1",
            "subject_type": "bridge",
            "display_name": "Win Bridge",
        }
    )
    admin = Principal("admin_1", "admin", frozenset({"admin:pairing"}))
    pairing.confirm(
        {
            "schema_version": "0.1",
            "pairing_id": challenge["pairing_id"],
            "user_code": challenge["user_code"],
            "approved": True,
        },
        admin=admin,
    )
    complete = pairing.complete(challenge["pairing_id"])
    token = complete["access_token"]

    directory = StoreBackedTokenDirectory(security_db)
    gate = ApiGate(directory)
    principal = gate.authorize("POST", "/v1/events/batch", f"Bearer {token}")
    assert principal is not None

    security_db.revoke_grant_by_token(token)
    from stackchan.contracts import AuthorizationError

    with pytest.raises(AuthorizationError) as exc:
        gate.authorize("POST", "/v1/events/batch", f"Bearer {token}")
    assert exc.value.code == "revoked"


def test_policy_version_and_revocation_fail_closed(policies: PolicyService) -> None:
    policies.publish(
        {
            "policy_id": "pol_home",
            "version": "v1",
            "privacy_mode": "private",
            "valid_until": _future(48),
        }
    )
    policies.bind_device("cores3_001", "pol_home", "v1")

    ok = policies.validate_device_presentation(
        "cores3_001",
        claimed_policy_version="v1",
    )
    assert ok.allowed is True

    mismatch = policies.validate_device_presentation(
        "cores3_001",
        claimed_policy_version="v0",
    )
    assert mismatch.allowed is False
    assert mismatch.reason == "policy_version_mismatch"

    policies.revoke("pol_home", "v1")
    revoked = policies.validate_device_presentation(
        "cores3_001",
        claimed_policy_version="v1",
    )
    assert revoked.allowed is False
    assert revoked.reason == "policy_revoked"


def test_expired_policy_fail_closed(policies: PolicyService) -> None:
    policies.publish(
        {
            "policy_id": "pol_old",
            "version": "v1",
            "privacy_mode": "strict",
            "valid_until": _past(),
        }
    )
    policies.bind_device("cores3_002", "pol_old", "v1")
    decision = policies.validate_device_presentation(
        "cores3_002",
        claimed_policy_version="v1",
    )
    assert decision.allowed is False
    assert decision.reason == "policy_expired"


def test_default_bind_host_and_reject_all_interfaces() -> None:
    assert DEFAULT_BIND_HOST == "127.0.0.1"
    assert assert_safe_bind_host("127.0.0.1") == "127.0.0.1"
    with pytest.raises(ExposureError):
        assert_safe_bind_host("0.0.0.0")
    with pytest.raises(ExposureError):
        assert_safe_bind_host("192.168.1.10")
    assert assert_safe_bind_host("192.168.1.10", allow_lan=True) == "192.168.1.10"


def test_redact_secrets_for_diagnostics() -> None:
    payload = {
        "access_token": "super-secret-token",
        "event_id": "evt_1",
        "nested": {"password": "p@ss", "ok": True},
    }
    redacted = redact_secrets(payload)
    assert redacted["access_token"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["event_id"] == "evt_1"
    assert redacted["nested"]["ok"] is True
