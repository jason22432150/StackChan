"""應用層語意不變式測試。"""

from __future__ import annotations

import pytest

from stackchan.contracts import (
    ContractSemanticsError,
    assert_event_semantics,
    implies_task_succeeded,
)


def test_response_completed_does_not_imply_success(valid_agent_event, mutate) -> None:
    event = mutate(
        valid_agent_event,
        event_type="response.completed",
        evidence_level="verified",
    )
    assert implies_task_succeeded(event) is False


def test_only_task_succeeded_implies_success(valid_agent_event, mutate) -> None:
    event = mutate(valid_agent_event, event_type="task.succeeded", evidence_level="verified")
    assert implies_task_succeeded(event) is True


def test_presentation_hint_task_succeeded_blocked_for_response_completed(
    valid_agent_event, mutate
) -> None:
    event = mutate(
        valid_agent_event,
        event_type="response.completed",
        _presentation_hint="task_succeeded",
    )
    with pytest.raises(ContractSemanticsError):
        assert_event_semantics(event)


def test_secret_source_payload_forbids_sensitive_keys(valid_agent_event, mutate) -> None:
    event = mutate(
        valid_agent_event,
        privacy_class="secret",
        source_payload={"prompt": "do not store"},
    )
    with pytest.raises(ContractSemanticsError):
        assert_event_semantics(event)
