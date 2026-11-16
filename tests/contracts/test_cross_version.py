"""跨版本與凍結版本行為。"""

from __future__ import annotations

import pytest

from stackchan.contracts import (
    CONTRACT_SCHEMA_VERSION,
    ContractValidationError,
    SchemaName,
    load_schema,
    validate_agent_event,
    validate_notification_intent,
    validate_presentation_receipt,
)


def test_frozen_schema_version_constant() -> None:
    assert CONTRACT_SCHEMA_VERSION == "0.1"


@pytest.mark.parametrize(
    "name",
    [
        SchemaName.AGENT_EVENT,
        SchemaName.NOTIFICATION_INTENT,
        SchemaName.PRESENTATION_RECEIPT,
    ],
)
def test_schemas_declare_frozen_const(name: SchemaName) -> None:
    schema = load_schema(name)
    assert schema["properties"]["schema_version"]["const"] == "0.1"
    assert "FROZEN" in schema["title"]


@pytest.mark.parametrize(
    ("validator", "fixture_name"),
    [
        (validate_agent_event, "valid_agent_event"),
        (validate_notification_intent, "valid_notification_intent"),
        (validate_presentation_receipt, "valid_presentation_receipt"),
    ],
)
@pytest.mark.parametrize("bad_version", ["0.0", "1.0", "0.1.0", "", None])
def test_unsupported_schema_versions_rejected(
    validator, fixture_name, bad_version, mutate, request
) -> None:
    base = request.getfixturevalue(fixture_name)
    if bad_version is None:
        payload = mutate(base, schema_version=Ellipsis)
    else:
        payload = mutate(base, schema_version=bad_version)
    with pytest.raises(ContractValidationError):
        validator(payload)
