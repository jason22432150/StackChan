"""Agent 通知平台契約驗證（FROZEN schema_version=0.1）。"""

from stackchan.contracts.authz import (
    ApiGate,
    AuthorizationError,
    Principal,
    TokenDirectory,
    find_route,
    load_route_requirements,
)
from stackchan.contracts.semantics import (
    ContractSemanticsError,
    assert_event_semantics,
    implies_task_succeeded,
)
from stackchan.contracts.validate import (
    CONTRACT_SCHEMA_VERSION,
    ContractValidationError,
    SchemaName,
    load_schema,
    validate_agent_event,
    validate_device_stream_envelope,
    validate_error,
    validate_notification_intent,
    validate_pairing_message,
    validate_payload,
    validate_presentation_receipt,
)

__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "ApiGate",
    "AuthorizationError",
    "ContractSemanticsError",
    "ContractValidationError",
    "Principal",
    "SchemaName",
    "TokenDirectory",
    "assert_event_semantics",
    "find_route",
    "implies_task_succeeded",
    "load_route_requirements",
    "load_schema",
    "validate_agent_event",
    "validate_device_stream_envelope",
    "validate_error",
    "validate_notification_intent",
    "validate_pairing_message",
    "validate_payload",
    "validate_presentation_receipt",
]
