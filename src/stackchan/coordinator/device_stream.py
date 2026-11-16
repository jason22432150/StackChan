"""Encode Coordinator-to-device heartbeats and intents for the device stream."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from stackchan.contracts.validate import (
    CONTRACT_SCHEMA_VERSION,
    ContractValidationError,
    validate_device_stream_envelope,
    validate_notification_intent,
)

_MAX_IDENTIFIER_BYTES = 128
_MAX_GENERATION = (1 << 64) - 1
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def encode_heartbeat(
    *, device_id: str, policy_version: str, generation: int, sent_at: datetime,
) -> bytes:
    """Encode a heartbeat for an already authenticated device session."""
    return _encode(
        "heartbeat", device_id, policy_version, generation, _utc_milliseconds(sent_at),
    )


def encode_notification_intent(intent: dict[str, Any], *, sent_at: datetime) -> bytes:
    """Encode a dispatcher-selected intent, deriving envelope scope from the payload."""
    validate_notification_intent(intent)
    sent = _utc_milliseconds(sent_at)
    try:
        expires = _utc_milliseconds(datetime.fromisoformat(intent["expires_at"].upper()))
    except (ValueError, OverflowError) as exc:
        raise ContractValidationError("invalid notification deadline", path=("expires_at",)) from exc
    if expires <= sent:
        raise ContractValidationError("notification expired at send time", path=("expires_at",))

    payload = {**intent, "expires_at": _timestamp(expires), "priority": int(intent["priority"])}
    return _encode(
        "notification.intent",
        intent["device_id"],
        intent["policy_version"],
        intent["generation"],
        sent,
        delivery_id=intent["delivery_id"],
        payload=payload,
    )


def _utc_milliseconds(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ContractValidationError("stream timestamp requires a timezone")
    try:
        utc = value.astimezone(timezone.utc)
    except OverflowError as exc:
        raise ContractValidationError("stream timestamp is out of range") from exc
    utc = utc.replace(microsecond=(utc.microsecond // 1000) * 1000)
    if utc <= _EPOCH:
        raise ContractValidationError("stream timestamp must be after the Unix epoch")
    return utc


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _validate_identifier(value: str, field: str) -> None:
    try:
        if isinstance(value, str) and "\0" not in value and 1 <= len(value.encode("utf-8")) <= _MAX_IDENTIFIER_BYTES:
            return
    except UnicodeEncodeError as exc:
        raise ContractValidationError("stream identifier must be valid UTF-8", path=(field,)) from exc
    raise ContractValidationError("stream identifier must fit in 128 UTF-8 bytes", path=(field,))


def _encode(
    frame_type: str,
    device_id: str,
    policy_version: str,
    generation: int,
    sent: datetime,
    *,
    delivery_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> bytes:
    _validate_identifier(device_id, "device_id")
    _validate_identifier(policy_version, "policy_version")
    if type(generation) is not int or not 0 <= generation <= _MAX_GENERATION:
        raise ContractValidationError("stream generation must be a uint64", path=("generation",))

    envelope = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "message_id": str(uuid4()),
        "device_id": device_id,
        "policy_version": policy_version,
        "generation": generation,
        "direction": "coordinator_to_device",
        "type": frame_type,
        "sent_at": _timestamp(sent),
    }
    if delivery_id is not None:
        _validate_identifier(delivery_id, "delivery_id")
        envelope.update(delivery_id=delivery_id, payload=payload)

    validate_device_stream_envelope(envelope)
    try:
        return json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ContractValidationError("stream payload must be valid UTF-8") from exc
