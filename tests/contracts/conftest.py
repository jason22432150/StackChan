"""契約測試共用 fixtures。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest


@pytest.fixture
def valid_agent_event() -> dict[str, Any]:
    """最小合法 AgentEvent。"""
    return {
        "schema_version": "0.1",
        "event_id": "evt_001",
        "observation_id": "obs_001",
        "bridge_id": "bridge_win_1",
        "adapter_id": "codex.hooks",
        "agent_id": "codex",
        "event_type": "task.started",
        "evidence_level": "observed",
        "privacy_class": "internal",
        "observed_at": "2026-11-16T12:00:00Z",
        "bridge_sequence": 1,
        "epoch": "epoch-1",
    }


@pytest.fixture
def valid_notification_intent() -> dict[str, Any]:
    """最小合法 NotificationIntent。"""
    return {
        "schema_version": "0.1",
        "notification_id": "ntf_001",
        "delivery_id": "dlv_001",
        "device_id": "cores3_001",
        "event_ids": ["evt_001"],
        "priority": 50,
        "policy_version": "pol-1",
        "generation": 1,
        "expires_at": "2026-11-16T13:00:00Z",
        "presentation_policy": {
            "ui": True,
            "audio": False,
            "motion": False,
            "tts": False,
        },
    }


@pytest.fixture
def valid_presentation_receipt() -> dict[str, Any]:
    """最小合法 PresentationReceipt。"""
    return {
        "schema_version": "0.1",
        "receipt_id": "rcp_001",
        "delivery_id": "dlv_001",
        "attempt_id": "att_001",
        "device_id": "cores3_001",
        "generation": 1,
        "status": "accepted",
        "reported_at": "2026-11-16T12:01:00Z",
    }


@pytest.fixture
def mutate():
    """回傳可覆寫欄位的深拷貝 helper。"""

    def _mutate(base: dict[str, Any], **overrides: Any) -> dict[str, Any]:
        payload = deepcopy(base)
        for key, value in overrides.items():
            if value is Ellipsis:
                payload.pop(key, None)
            else:
                payload[key] = value
        return payload

    return _mutate
