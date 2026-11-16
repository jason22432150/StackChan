"""AgentEvent schema 合法／非法案例。"""

from __future__ import annotations

import pytest

from stackchan.contracts import ContractValidationError, validate_agent_event


def test_valid_agent_event_passes(valid_agent_event) -> None:
    assert validate_agent_event(valid_agent_event)["event_id"] == "evt_001"


def test_response_completed_is_valid_but_not_success_type(valid_agent_event, mutate) -> None:
    payload = mutate(valid_agent_event, event_type="response.completed", evidence_level="verified")
    validated = validate_agent_event(payload)
    assert validated["event_type"] == "response.completed"
    assert validated["event_type"] != "task.succeeded"


@pytest.mark.parametrize(
    "overrides",
    [
        {"event_id": Ellipsis},
        {"schema_version": Ellipsis},
        {"bridge_sequence": 0},
        {"event_type": "task.finished"},
        {"evidence_level": "sure"},
        {"privacy_class": "top-secret"},
        {"observed_at": "yesterday"},
        {"extra_field": "nope"},
        {"source_payload": {"prompt": "x", "nested": {"a": 1}}},
    ],
)
def test_illegal_agent_events_rejected(valid_agent_event, mutate, overrides) -> None:
    payload = mutate(valid_agent_event, **overrides)
    with pytest.raises(ContractValidationError):
        validate_agent_event(payload)


def test_source_payload_allowlisted_scalars(valid_agent_event, mutate) -> None:
    payload = mutate(
        valid_agent_event,
        source_payload={"cwd": "/tmp", "exit_code": 0, "ok": True, "note": None},
    )
    assert validate_agent_event(payload)["source_payload"]["exit_code"] == 0
