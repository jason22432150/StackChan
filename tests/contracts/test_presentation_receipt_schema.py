"""PresentationReceipt schema 合法／非法案例。"""

from __future__ import annotations

import pytest

from stackchan.contracts import ContractValidationError, validate_presentation_receipt


def test_valid_presentation_receipt_passes(valid_presentation_receipt) -> None:
    assert validate_presentation_receipt(valid_presentation_receipt)["status"] == "accepted"


@pytest.mark.parametrize(
    "status",
    ["accepted", "started", "completed", "interrupted", "cancelled", "failed"],
)
def test_all_receipt_statuses_allowed(valid_presentation_receipt, mutate, status) -> None:
    payload = mutate(valid_presentation_receipt, status=status)
    assert validate_presentation_receipt(payload)["status"] == status


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": Ellipsis},
        {"status": "delivered"},
        {"reported_at": "16/11/2026"},
        {"generation": -1},
        {"reason": "x" * 129},
        {"hack": 1},
    ],
)
def test_illegal_presentation_receipts_rejected(
    valid_presentation_receipt, mutate, overrides
) -> None:
    payload = mutate(valid_presentation_receipt, **overrides)
    with pytest.raises(ContractValidationError):
        validate_presentation_receipt(payload)
