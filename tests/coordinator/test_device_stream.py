import json
from datetime import datetime, timezone
from uuid import UUID

import pytest

from stackchan.contracts.validate import ContractValidationError, validate_device_stream_envelope
from stackchan.coordinator.device_stream import encode_heartbeat, encode_notification_intent

SENT_AT = datetime.fromisoformat("2026-11-16T20:00:00.123999+08:00")


def test_heartbeat_wire_format_and_message_id():
    fields = {"device_id": "桌面", "policy_version": "v1", "generation": 0, "sent_at": SENT_AT}
    first = validate_device_stream_envelope(json.loads(encode_heartbeat(**fields)))
    second = json.loads(encode_heartbeat(**fields))
    assert UUID(first["message_id"]).version == 4
    assert first["message_id"] != second["message_id"]
    assert first["sent_at"] == "2026-11-16T12:00:00.123Z"
    assert first["direction"] == "coordinator_to_device"
    assert first["device_id"] == "桌面"
    assert first["type"] == "heartbeat"
    assert "delivery_id" not in first
    assert "payload" not in first


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("device_id", ""),
        ("device_id", "機" * 43),
        ("device_id", "bad\0id"),
        ("policy_version", "\ud800"),
        ("generation", -1),
        ("generation", 1 << 64),
        ("generation", True),
        ("generation", 1.0),
        ("sent_at", datetime(2026, 11, 16)),
        ("sent_at", datetime(1970, 1, 1, tzinfo=timezone.utc)),
    ],
)
def test_wire_constraints_reject_unusable_heartbeat_values(field, value):
    fields = {"device_id": "device", "policy_version": "v1", "generation": 1, "sent_at": SENT_AT}
    fields[field] = value
    with pytest.raises(ContractValidationError):
        encode_heartbeat(**fields)


def test_heartbeat_accepts_largest_wire_scope_values():
    device = "機" * 42 + "ab"
    envelope = json.loads(
        encode_heartbeat(device_id=device, policy_version="v1", generation=(1 << 64) - 1, sent_at=SENT_AT)
    )
    assert envelope["generation"] == (1 << 64) - 1
    assert len(envelope["device_id"].encode("utf-8")) == 128


@pytest.fixture
def intent():
    return {
        "schema_version": "0.1",
        "notification_id": "notification",
        "delivery_id": "delivery",
        "device_id": "device",
        "event_ids": ["event"],
        "priority": 10,
        "policy_version": "v1",
        "generation": 1,
        "expires_at": "2026-11-16T20:00:01.123999+08:00",
        "presentation_policy": {"ui": True, "audio": False, "motion": False, "tts": False},
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "1.0"),
        ("delivery_id", "機" * 43),
        ("event_ids", []),
        ("expires_at", "2026-11-16T12:00:00.123400Z"),
        ("expires_at", "2026-11-16T12:00:00.122Z"),
        ("generation", 1 << 64),
    ],
)
def test_intent_schema_and_wire_expiry_boundary(intent, field, value):
    intent[field] = value
    with pytest.raises(ContractValidationError):
        encode_notification_intent(intent, sent_at=SENT_AT)


def test_intent_deadline_normalization_preserves_original(intent):
    before = intent.copy()
    wire = json.loads(encode_notification_intent(intent, sent_at=SENT_AT))
    assert wire["payload"] == {**before, "expires_at": "2026-11-16T12:00:01.123Z"}
    assert intent == before
