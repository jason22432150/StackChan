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


_SCHEMA_FILES = {
    SchemaName.AGENT_EVENT: "agent-event.schema.json",
    SchemaName.NOTIFICATION_INTENT: "notification-intent.schema.json",
    SchemaName.PRESENTATION_RECEIPT: "presentation-receipt.schema.json",
}


class ContractValidationError(ValueError):
    """契約驗證失敗。"""

    def __init__(self, message: str, *, path: tuple[Any, ...] = ()) -> None:
        super().__init__(message)
        self.path = path


@lru_cache(maxsize=8)
def load_schema(name: SchemaName) -> dict[str, Any]:
    """載入並快取指定凍結 schema。"""
    path = contracts_dir() / _SCHEMA_FILES[name]
    with path.open(encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return schema


def _validator(name: SchemaName) -> Draft202012Validator:
    return Draft202012Validator(
        load_schema(name),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def validate_payload(name: SchemaName, payload: Any) -> dict[str, Any]:
    """
    驗證 payload 符合凍結 schema。

    Returns:
        通過驗證的 dict（便於後續流水線使用）。
    """
    if not isinstance(payload, dict):
        raise ContractValidationError("payload 必須為 JSON object")

    version = payload.get("schema_version")
    if version != CONTRACT_SCHEMA_VERSION:
        raise ContractValidationError(
            f"不支援的 schema_version={version!r}；凍結版本為 {CONTRACT_SCHEMA_VERSION!r}",
            path=("schema_version",),
        )

    validator = _validator(name)
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
    if errors:
        first = errors[0]
        path = tuple(first.path)
        raise ContractValidationError(first.message, path=path)
    return payload


def validate_agent_event(payload: Any) -> dict[str, Any]:
    """驗證 AgentEvent。"""
    return validate_payload(SchemaName.AGENT_EVENT, payload)


def validate_notification_intent(payload: Any) -> dict[str, Any]:
    """驗證 NotificationIntent。"""
    return validate_payload(SchemaName.NOTIFICATION_INTENT, payload)


def validate_presentation_receipt(payload: Any) -> dict[str, Any]:
    """驗證 PresentationReceipt。"""
    return validate_payload(SchemaName.PRESENTATION_RECEIPT, payload)


# 避免未使用 import 警告（ValidationError 供測試 re-export 時可選）
_ = ValidationError
