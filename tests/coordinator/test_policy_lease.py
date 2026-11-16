"""P2-04 政策租約交換：授權、Fail-Closed、OpenAPI 欄位與 expires_utc_ms。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from stackchan.contracts.authz import ApiGate, AuthorizationError, Principal, TokenDirectory
from stackchan.coordinator.policy_lease import DevicePolicyLeaseService, PolicyLease
from stackchan.security.identity import TokenHasher
from stackchan.security.policy import PolicyError, PolicyService
from stackchan.security.store import SecurityStore


def _future(hours: int = 24) -> str:
    return (
        datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=hours)
    ).isoformat().replace("+00:00", "Z")


def _past() -> str:
    return (
        datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
    ).isoformat().replace("+00:00", "Z")


@pytest.fixture
def lease_env(tmp_path):
    store = SecurityStore(tmp_path / "security.sqlite3", hasher=TokenHasher(pepper=b"lease"))
    tokens = TokenDirectory()
    policies = PolicyService(store)
    policies.publish(
        {
            "policy_id": "desk",
            "version": "v1",
            "privacy_mode": "private",
            "valid_until": _future(12),
        }
    )
    for device, token, scopes in (
        ("cores3_desk", "device-ok", frozenset({"device:policy", "device:stream"})),
        ("cores3_desk", "device-stream-only", frozenset({"device:stream"})),
        ("cores3_other", "device-other", frozenset({"device:policy", "device:stream"})),
        ("bridge_1", "bridge-token", frozenset({"bridge:write"})),
    ):
        subject_type = "bridge" if device.startswith("bridge") else "device"
        store.upsert_subject(device, subject_type, device)
        tokens.issue(token, Principal(device, subject_type, scopes))
    policies.bind_device("cores3_desk", "desk", "v1")
    policies.bind_device("cores3_other", "desk", "v1")
    gate = ApiGate(tokens)
    service = DevicePolicyLeaseService(gate, policies)
    yield service, policies, tokens
    store.close()


def test_authorized_device_receives_lease_snapshot(lease_env) -> None:
    service, _, _ = lease_env
    lease = service.get_device_policy(
        "cores3_desk",
        authorization_header="Bearer device-ok",
    )
    assert isinstance(lease, PolicyLease)
    assert lease.policy_id == "desk"
    assert lease.version == "v1"
    assert lease.privacy_mode == "private"
    assert lease.expires_utc_ms > 0
    body = lease.as_openapi_policy()
    assert set(body) == {"policy_id", "version", "privacy_mode", "valid_until"}
    assert "revoked" not in body
    assert body["valid_until"] == lease.valid_until


def test_missing_wrong_scope_and_cross_device_are_forbidden(lease_env) -> None:
    service, _, _ = lease_env
    with pytest.raises(AuthorizationError) as missing:
        service.get_device_policy("cores3_desk", authorization_header=None)
    assert missing.value.http_status == 401

    with pytest.raises(AuthorizationError) as wrong_scope:
        service.get_device_policy(
            "cores3_desk",
            authorization_header="Bearer device-stream-only",
        )
    assert wrong_scope.value.http_status == 403
    assert wrong_scope.value.code == "forbidden"

    with pytest.raises(AuthorizationError) as cross_device:
        service.get_device_policy(
            "cores3_desk",
            authorization_header="Bearer device-other",
        )
    assert cross_device.value.http_status == 403

    with pytest.raises(AuthorizationError) as bridge:
        service.get_device_policy(
            "cores3_desk",
            authorization_header="Bearer bridge-token",
        )
    assert bridge.value.http_status == 403


def test_revoked_and_expired_leases_fail_closed(lease_env) -> None:
    service, policies, _ = lease_env
    policies.revoke("desk", "v1")
    with pytest.raises(AuthorizationError) as revoked:
        service.get_device_policy(
            "cores3_desk",
            authorization_header="Bearer device-ok",
        )
    assert revoked.value.http_status == 403
    assert "policy_revoked" in revoked.value.message

    policies.publish(
        {
            "policy_id": "desk",
            "version": "v2",
            "privacy_mode": "strict",
            "valid_until": _past(),
        }
    )
    policies.bind_device("cores3_desk", "desk", "v2")
    with pytest.raises(AuthorizationError) as expired:
        service.get_device_policy(
            "cores3_desk",
            authorization_header="Bearer device-ok",
        )
    assert expired.value.http_status == 403
    assert "policy_expired" in expired.value.message


def test_unbound_device_and_version_mismatch_fail_closed(lease_env) -> None:
    service, policies, tokens = lease_env
    tokens.issue(
        "device-unbound",
        Principal("cores3_new", "device", frozenset({"device:policy"})),
    )
    with pytest.raises(AuthorizationError) as unbound:
        service.get_device_policy(
            "cores3_new",
            authorization_header="Bearer device-unbound",
        )
    assert unbound.value.http_status == 403
    assert "device_unbound" in unbound.value.message

    with pytest.raises(PolicyError, match="policy_version_mismatch"):
        policies.issue_device_lease("cores3_desk", claimed_policy_version="nope")


def test_lease_expires_utc_ms_matches_valid_until(lease_env) -> None:
    service, _, _ = lease_env
    lease = service.get_device_policy(
        "cores3_desk",
        authorization_header="Bearer device-ok",
    )
    expected = int(
        datetime.fromisoformat(lease.valid_until.upper())
        .astimezone(timezone.utc)
        .timestamp()
        * 1000
    )
    assert lease.expires_utc_ms == expected
