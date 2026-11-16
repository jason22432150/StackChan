"""契約語意守衛（規格無法僅用 JSON Schema 表達的不變式）。"""

from __future__ import annotations

from typing import Any, Mapping


class ContractSemanticsError(ValueError):
    """語意規則違反。"""


def implies_task_succeeded(event: Mapping[str, Any]) -> bool:
    """
    是否可宣稱任務成功。

    僅 `event_type == task.succeeded` 為真；
    `response.completed` 即使 evidence_level=verified 也不得推導成功。
    """
    return event.get("event_type") == "task.succeeded"


def assert_event_semantics(event: Mapping[str, Any]) -> None:
    """
    檢查 AgentEvent 應用層語意。

    目前強制：不得把非 succeeded 類型標記成「可當成功通知」的衍生旗標。
    若呼叫端傳入 `_presentation_hint == "task_succeeded"` 且類型不符則拒絕。
    """
    hint = event.get("_presentation_hint")
    if hint == "task_succeeded" and not implies_task_succeeded(event):
        raise ContractSemanticsError(
            "response.completed／非 succeeded 事件不得以 task_succeeded 呈現"
        )

    # 敏感預設：secret 類不得預設要求 tts（此欄在 Event 上；Intent 另審）
    if event.get("privacy_class") == "secret" and event.get("source_payload"):
        # source_payload 僅允許白名單純量；禁止常見敏感鍵名
        forbidden = {"prompt", "password", "token", "api_key", "authorization"}
        keys = {str(key).lower() for key in event["source_payload"]}
        leaked = keys & forbidden
        if leaked:
            raise ContractSemanticsError(f"source_payload 含禁止鍵: {sorted(leaked)}")
