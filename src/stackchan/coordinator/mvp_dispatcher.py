"""以 CORE_S3_MVP_RUNTIME_LIMITS 建立 NotificationDispatcher。"""

from __future__ import annotations

from datetime import datetime
from typing import Callable
from time import monotonic

from stackchan.contracts.authz import TokenDirectory
from stackchan.coordinator.dispatch import NotificationDispatcher
from stackchan.coordinator.runtime_limits import (
    CORE_S3_MVP_RUNTIME_LIMITS,
    validate_coordinator_runtime_limits,
)
from stackchan.security.policy import PolicyService


def create_mvp_notification_dispatcher(
    tokens: TokenDirectory,
    policies: PolicyService,
    *,
    stable_seconds: float | None = None,
    heartbeat_timeout: float | None = None,
    capacity: int | None = None,
    priority_burst: int = 3,
    steady_clock: Callable[[], float] = monotonic,
    utc_clock: Callable[[], datetime] | None = None,
) -> NotificationDispatcher:
    """
    使用已驗證的 MVP 容量／逾時建立派送器。

    測試可覆寫 stable_seconds 以縮短穩定門檻；未覆寫時使用正式 5s。
    """
    limits = validate_coordinator_runtime_limits(CORE_S3_MVP_RUNTIME_LIMITS)
    kwargs: dict = {
        "stable_seconds": limits.stability_seconds if stable_seconds is None else stable_seconds,
        "heartbeat_timeout": (
            limits.heartbeat_timeout_seconds if heartbeat_timeout is None else heartbeat_timeout
        ),
        "capacity": limits.device_queue_capacity if capacity is None else capacity,
        "priority_burst": priority_burst,
        "steady_clock": steady_clock,
    }
    if utc_clock is not None:
        kwargs["utc_clock"] = utc_clock
    if kwargs["capacity"] > limits.device_queue_capacity:
        raise ValueError("capacity 不可超過 MVP device_queue_capacity")
    return NotificationDispatcher(tokens, policies, **kwargs)
