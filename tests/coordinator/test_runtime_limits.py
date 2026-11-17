"""P2-04 Coordinator／CoreS3 正式容量與逾時預設對齊測試。"""

from __future__ import annotations

import pytest

from stackchan.coordinator.dispatch import NotificationDispatcher
from stackchan.coordinator.runtime_limits import (
    CORE_S3_MVP_RUNTIME_LIMITS,
    P004_MAX_UI_UPDATE_GAP_MS,
    CoordinatorRuntimeLimits,
    mvp_soft_worst_case_revoke_ms,
    validate_coordinator_runtime_limits,
)
from stackchan.contracts.authz import Principal, TokenDirectory
from stackchan.security.identity import TokenHasher
from stackchan.security.policy import PolicyService
from stackchan.security.store import SecurityStore


def test_mvp_limits_match_device_profile() -> None:
    limits = validate_coordinator_runtime_limits(CORE_S3_MVP_RUNTIME_LIMITS)
    assert limits.device_queue_capacity == 4
    assert limits.heartbeat_timeout_seconds == 4.0
    assert limits.stability_seconds == 5.0
    assert limits.heartbeat_interval_seconds == 1.0
    assert limits.pong_timeout_seconds == 2.0
    assert limits.max_frame_age_seconds == 5.0
    assert limits.max_frame_bytes == 1024
    assert limits.heartbeat_interval_seconds < limits.heartbeat_timeout_seconds
    assert limits.pong_timeout_seconds < limits.heartbeat_timeout_seconds


def test_r006_soft_worst_case_revoke_budget_matches_firmware() -> None:
    """R-006 軟路徑：與 firmware kMvpSoftWorstCaseRevokeMs=4185 對齊。"""
    assert P004_MAX_UI_UPDATE_GAP_MS == 185
    assert mvp_soft_worst_case_revoke_ms() == 4185
    assert mvp_soft_worst_case_revoke_ms(CORE_S3_MVP_RUNTIME_LIMITS) == 4000 + 185


def test_invalid_limits_fail_closed() -> None:
    with pytest.raises(ValueError):
        validate_coordinator_runtime_limits(
            CoordinatorRuntimeLimits(device_queue_capacity=5)
        )
    with pytest.raises(ValueError):
        validate_coordinator_runtime_limits(
            CoordinatorRuntimeLimits(heartbeat_interval_seconds=5.0, heartbeat_timeout_seconds=4.0)
        )
    with pytest.raises(ValueError):
        validate_coordinator_runtime_limits(
            CoordinatorRuntimeLimits(max_frame_bytes=0)
        )


def test_dispatcher_accepts_mvp_limits(tmp_path) -> None:
    limits = validate_coordinator_runtime_limits(CORE_S3_MVP_RUNTIME_LIMITS)
    store = SecurityStore(tmp_path / "security.sqlite3", hasher=TokenHasher(pepper=b"limits"))
    tokens = TokenDirectory()
    policies = PolicyService(store)
    policies.publish(
        {
            "policy_id": "desk",
            "version": "v1",
            "privacy_mode": "private",
            "valid_until": "2099-01-01T00:00:00Z",
        }
    )
    store.upsert_subject("device", "device", "device")
    tokens.issue(
        "token",
        Principal("device", "device", frozenset({"device:stream"})),
    )
    policies.bind_device("device", "desk", "v1")
    dispatcher = NotificationDispatcher(
        tokens,
        policies,
        stable_seconds=limits.stability_seconds,
        heartbeat_timeout=limits.heartbeat_timeout_seconds,
        capacity=limits.device_queue_capacity,
    )
    assert dispatcher.connect("device", "token", "v1") is not None
    store.close()
