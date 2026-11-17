"""P2-07：裝置端 compact JSON 金樣必須通過 PresentationReceipt 契約。"""

from __future__ import annotations

from stackchan.contracts import validate_presentation_receipt

# 與 firmware/tests/presentation_receipt_test.cpp::testEncodeGoldenEpochSample 對齊。
DEVICE_ENCODED_ACCEPTED = (
    '{"schema_version":"0.1","receipt_id":"rcp_001","delivery_id":"dlv_001",'
    '"attempt_id":"att_001","device_id":"cores3_001","generation":1,"status":"accepted",'
    '"reported_at":"1970-01-01T00:00:00.000Z"}'
)

DEVICE_ENCODED_INTERRUPTED = (
    '{"schema_version":"0.1","receipt_id":"rcp_i","delivery_id":"dlv_001",'
    '"attempt_id":"att_001","device_id":"cores3_001","generation":1,"status":"interrupted",'
    '"reason":"xiaozhi.busy","reported_at":"1970-01-01T00:00:01.000Z"}'
)


def test_device_encoded_accepted_passes_contract() -> None:
    import json

    payload = json.loads(DEVICE_ENCODED_ACCEPTED)
    assert validate_presentation_receipt(payload)["status"] == "accepted"


def test_device_encoded_interrupted_with_reason_passes_contract() -> None:
    import json

    payload = json.loads(DEVICE_ENCODED_INTERRUPTED)
    assert validate_presentation_receipt(payload)["reason"] == "xiaozhi.busy"
