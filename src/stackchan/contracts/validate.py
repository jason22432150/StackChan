"""JSON Schema 載入與 Draft 2020-12 驗證。"""

from __future__ import annotations

import json
from enum import Enum
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from stackchan.contracts.paths import contracts_dir

CONTRACT_SCHEMA_VERSION = "0.1"


class SchemaName(str, Enum):
    """凍結契約名稱。"""

    AGENT_EVENT = "agent-event"
    NOTIFICATION_INTENT = "notification-intent"
    PRESENTATION_RECEIPT = "presentation-receipt"
    ERROR = "error"
    DEVICE_STREAM_ENVELOPE = "device-stream-envelope"


_SCHEMA_FILES = {
    SchemaName.AGENT_EVENT: "agent-event.schema.json",
    SchemaName.NOTIFICATION_INTENT: "notification-intent.schema.json",
    SchemaName.PRESENTATION_RECEIPT: "presentation-receipt.schema.json",
    SchemaName.ERROR: "error.schema.json",
    SchemaName.DEVICE_STREAM_ENVELOPE: "device-stream-envelope.schema.json",
}

_PAIRING_DEFS = (
    "PairingStartRequest",
    "PairingChallenge",
    "PairingConfirmRequest",
    "PairingCompleteResponse",
)


class ContractValidationError(ValueError):
    """契約驗證失敗。"""

    def __init__(self, message: str, *, path: tuple[Any, ...] = ()) -> None:
        super().__init__(message)
        self.path = path


@lru_cache(maxsize=16)
def load_schema(name: SchemaName) -> dict[str, Any]:
    """載入並快取指定凍結 schema。"""
    path = contracts_dir() / _SCHEMA_FILES[name]
    with path.open(encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return schema


@lru_cache(maxsize=1)
def _pairing_document() -> dict[str, Any]:
    path = contracts_dir() / "pairing.schema.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _run_validator(validator: Draft202012Validator, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractValidationError("payload 必須為 JSON object")

    version = payload.get("schema_version")
    if version != CONTRACT_SCHEMA_VERSION:
        raise ContractValidationError(
            f"不支援的 schema_version={version!r}；凍結版本為 {CONTRACT_SCHEMA_VERSION!r}",
            path=("schema_version",),
        )

    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
    if errors:
        first = errors[0]
        raise ContractValidationError(first.message, path=tuple(first.path))
    return payload


def _validator(name: SchemaName) -> Draft202012Validator:
    return Draft202012Validator(
        load_schema(name),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def validate_payload(name: SchemaName, payload: Any) -> dict[str, Any]:
    """驗證 payload 符合凍結 schema。"""
    return _run_validator(_validator(name), payload)


def validate_agent_event(payload: Any) -> dict[str, Any]:
    """驗證 AgentEvent。"""
    return validate_payload(SchemaName.AGENT_EVENT, payload)


def validate_notification_intent(payload: Any) -> dict[str, Any]:
    """驗證 NotificationIntent。"""
    return validate_payload(SchemaName.NOTIFICATION_INTENT, payload)


def validate_presentation_receipt(payload: Any) -> dict[str, Any]:
    """驗證 PresentationReceipt。"""
    return validate_payload(SchemaName.PRESENTATION_RECEIPT, payload)


def validate_error(payload: Any) -> dict[str, Any]:
    """驗證 API Error。"""
    return validate_payload(SchemaName.ERROR, payload)


def validate_device_stream_envelope(payload: Any) -> dict[str, Any]:
    """驗證 Device Stream Envelope。"""
    return validate_payload(SchemaName.DEVICE_STREAM_ENVELOPE, payload)


def validate_pairing_message(def_name: str, payload: Any) -> dict[str, Any]:
    """驗證 pairing.schema.json 內指定 $defs 訊息。"""
    if def_name not in _PAIRING_DEFS:
        raise ContractValidationError(f"未知 pairing def: {def_name}")
    schema = _pairing_document()["$defs"][def_name]
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(
        schema,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    return _run_validator(validator, payload)


# 保留 ValidationError 名稱供測試／除錯引用
_ = ValidationError
