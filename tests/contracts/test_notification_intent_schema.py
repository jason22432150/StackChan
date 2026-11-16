"""NotificationIntent schema 合法／非法案例。"""

from __future__ import annotations

import pytest

from stackchan.contracts import ContractValidationError, validate_notification_intent


def test_valid_notification_intent_passes(valid_notification_intent) -> None:
    assert validate_notification_intent(valid_notification_intent)["delivery_id"] == "dlv_001"


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": Ellipsis},
        {"event_ids": []},
        {"event_ids": ["a", "a"]},
        {"priority": 101},
        {"generation": -1},
        {"expires_at": "not-a-date"},
        {"presentation_policy": {"ui": True, "audio": False, "motion": False}},
        {"unknown": True},
    ],
)
def test_illegal_notification_intents_rejected(
    valid_notification_intent, mutate, overrides
) -> None:
    payload = mutate(valid_notification_intent, **overrides)
    with pytest.raises(ContractValidationError):
        validate_notification_intent(payload)
