"""Agent 通知平台契約驗證（FROZEN schema_version=0.1）。"""

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
    validate_notification_intent,
    validate_presentation_receipt,
    validate_payload,
)

__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "ContractSemanticsError",
    "ContractValidationError",
    "SchemaName",
    "assert_event_semantics",
    "implies_task_succeeded",
    "load_schema",
    "validate_agent_event",
    "validate_notification_intent",
    "validate_payload",
    "validate_presentation_receipt",
]
