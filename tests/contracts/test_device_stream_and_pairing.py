"""Device Stream Envelope、Error 與 Pairing 契約測試。"""

from __future__ import annotations

from copy import deepcopy

import pytest

from stackchan.contracts import (
    ContractValidationError,
    validate_device_stream_envelope,
    validate_error,
    validate_notification_intent,
    validate_pairing_message,
)


@pytest.fixture
def valid_envelope() -> dict:
    return {
        "schema_version": "0.1",
        "message_id": "msg_001",
        "device_id": "cores3_001",
        "direction": "coordinator_to_device",
        "type": "heartbeat",
        "sent_at": "2026-11-16T12:00:00Z",
        "generation": 0,
        "policy_version": "pol-1",
        "payload": {"ok": True},
    }


def test_valid_device_stream_envelope(valid_envelope) -> None:
    assert validate_device_stream_envelope(valid_envelope)["type"] == "heartbeat"


def test_notification_intent_envelope_payload_validated_separately(
    valid_envelope, valid_notification_intent
) -> None:
    envelope = deepcopy(valid_envelope)
    envelope["type"] = "notification.intent"
    envelope["delivery_id"] = "dlv_001"
    envelope["payload"] = valid_notification_intent
    validate_device_stream_envelope(envelope)
    validate_notification_intent(envelope["payload"])


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": "1.0"},
        {"type": "notify"},
        {"direction": "sideways"},
        {"generation": -1},
        {"extra": True},
    ],
)
def test_illegal_envelopes_rejected(valid_envelope, overrides) -> None:
    payload = deepcopy(valid_envelope)
    payload.update(overrides)
    with pytest.raises(ContractValidationError):
        validate_device_stream_envelope(payload)


def test_valid_error_schema() -> None:
    error = {
        "schema_version": "0.1",
        "error": "unauthorized",
        "message": "缺少 Bearer token",
        "retryable": False,
    }
    assert validate_error(error)["error"] == "unauthorized"


def test_illegal_error_code_rejected() -> None:
    with pytest.raises(ContractValidationError):
        validate_error(
            {
                "schema_version": "0.1",
                "error": "teapot",
                "message": "no",
            }
        )


def test_pairing_flow_messages() -> None:
    start = {
        "schema_version": "0.1",
        "subject_type": "device",
        "display_name": "CoreS3 Desk",
        "client_public_key": None,
    }
    validate_pairing_message("PairingStartRequest", start)

    challenge = {
        "schema_version": "0.1",
        "pairing_id": "pair_1",
        "subject_type": "device",
        "user_code": "AB12",
        "expires_at": "2026-11-16T12:10:00Z",
    }
    validate_pairing_message("PairingChallenge", challenge)

    confirm = {
        "schema_version": "0.1",
        "pairing_id": "pair_1",
        "user_code": "AB12",
        "approved": True,
    }
    validate_pairing_message("PairingConfirmRequest", confirm)

    complete = {
        "schema_version": "0.1",
        "pairing_id": "pair_1",
        "subject_id": "cores3_001",
        "subject_type": "device",
        "access_token": "opaque-token-value-16",
        "scopes": ["device:stream", "device:receipt", "device:policy"],
        "token_expires_at": "2026-11-16T13:00:00Z",
    }
    validate_pairing_message("PairingCompleteResponse", complete)


def test_pairing_rejects_short_token() -> None:
    with pytest.raises(ContractValidationError):
        validate_pairing_message(
            "PairingCompleteResponse",
            {
                "schema_version": "0.1",
                "pairing_id": "pair_1",
                "subject_id": "cores3_001",
                "subject_type": "device",
                "access_token": "short",
                "scopes": ["device:stream"],
                "token_expires_at": "2026-11-16T13:00:00Z",
            },
        )
