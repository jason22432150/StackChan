"""Coordinator 端的通知排程與裝置派送授權。"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from hmac import compare_digest
from math import isfinite
from sqlite3 import Error as DatabaseError
from time import monotonic
from typing import Any, Callable
from uuid import UUID, uuid4

from stackchan.contracts.authz import TokenDirectory
from stackchan.contracts.validate import validate_notification_intent
from stackchan.security.policy import PolicyService


@dataclass(slots=True)
class _Session:
    session_id: UUID
    token_digest: bytes = field(repr=False)
    policy_id: str | None
    policy_version: str
    connected_at: float
    last_heartbeat: float
    consecutive_priority: int = 0


@dataclass(frozen=True, slots=True)
class _QueuedIntent:
    payload: dict[str, Any]
    expires_at: datetime
    policy_id: str | None


class NotificationDispatcher:
    """單一 Coordinator 執行迴圈擁有的暫態佇列。

    可信的 Coordinator 呼叫 enqueue，裝置 transport 呼叫其餘派送方法。
    呼叫端應在同一執行迴圈序列化操作，並將回傳的意圖交給目前連線。
    """

    def __init__(
        self,
        tokens: TokenDirectory,
        policies: PolicyService,
        *,
        stable_seconds: float,
        heartbeat_timeout: float,
        capacity: int,
        priority_burst: int = 3,
        steady_clock: Callable[[], float] = monotonic,
        utc_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if (
            not isfinite(stable_seconds) or stable_seconds <= 0
            or not isfinite(heartbeat_timeout) or heartbeat_timeout <= 0
            or capacity < 1 or priority_burst < 1
        ):
            raise ValueError("派送時間與佇列上限必須為正值")
        self._tokens = tokens
        self._policies = policies
        self._stable_seconds = stable_seconds
        self._heartbeat_timeout = heartbeat_timeout
        self._capacity = capacity
        self._priority_burst = priority_burst
        self._steady_clock = steady_clock
        self._utc_clock = utc_clock
        self._sessions: dict[str, _Session] = {}
        self._pending: dict[str, _QueuedIntent] = {}
        self._diagnostics: Counter[str] = Counter()

    def diagnostics(self) -> dict[str, int]:
        """回傳固定原因的累計次數。"""
        return dict(self._diagnostics)

    def _expire(self, now: datetime) -> None:
        expired = [
            delivery_id for delivery_id, entry in self._pending.items()
            if entry.expires_at <= now
        ]
        for delivery_id in expired:
            del self._pending[delivery_id]
        if expired:
            self._diagnostics["intent_expired"] += len(expired)

    def enqueue(self, intent: dict[str, Any]) -> bool:
        validate_notification_intent(intent)
        now = self._utc_clock()
        self._expire(now)
        expires_at = datetime.fromisoformat(intent["expires_at"].upper())
        if expires_at <= now:
            self._diagnostics["intent_expired"] += 1
            return False
        delivery_id = intent["delivery_id"]
        if delivery_id in self._pending:
            self._diagnostics["duplicate_pending_delivery"] += 1
            return False
        if len(self._pending) >= self._capacity:
            self._diagnostics["queue_full"] += 1
            return False
        decision = self._policies.validate_device_presentation(
            intent["device_id"], claimed_policy_version=intent["policy_version"],
            now=now.isoformat(),
        )
        if not decision.allowed:
            self._diagnostics[decision.reason] += 1
            return False
        self._pending[delivery_id] = _QueuedIntent(
            deepcopy(intent), expires_at, decision.policy_id,
        )
        return True

    def _authenticate(self, device_id: str, token: str) -> bool:
        principal = self._tokens.resolve(token)
        allowed = (
            principal is not None
            and not principal.revoked
            and principal.subject_type == "device"
            and principal.subject_id == device_id
            and "device:stream" in principal.scopes
        )
        if not allowed:
            self._diagnostics["device_unauthorized"] += 1
        return allowed

    def connect(self, device_id: str, token: str, policy_version: str) -> UUID | None:
        """建立 RECOVERING 連線。每次成功重連都重新計算穩定時間。"""
        if not self._authenticate(device_id, token):
            return None
        decision = self._policies.validate_device_presentation(
            device_id, claimed_policy_version=policy_version,
            now=self._utc_clock().isoformat(),
        )
        if not decision.allowed:
            self._diagnostics[decision.reason] += 1
            return None
        now = self._steady_clock()
        session_id = uuid4()
        self._sessions[device_id] = _Session(
            session_id, sha256(token.encode()).digest(), decision.policy_id, policy_version, now, now,
        )
        return session_id

    def disconnect(self, device_id: str, session_id: UUID) -> None:
        session = self._sessions.get(device_id)
        if session is not None and session.session_id == session_id:
            del self._sessions[device_id]
            self._diagnostics["disconnected"] += 1

    def _check_session(
        self, device_id: str, session_id: UUID, token: str,
        now: float, checked_at: datetime,
    ) -> _Session | None:
        session = self._sessions.get(device_id)
        if session is None or session.session_id != session_id:
            self._diagnostics["stale_session"] += 1
            return None
        if not compare_digest(session.token_digest, sha256(token.encode()).digest()):
            self._diagnostics["device_unauthorized"] += 1
            return None
        if now - session.last_heartbeat >= self._heartbeat_timeout:
            del self._sessions[device_id]
            self._diagnostics["heartbeat_timeout"] += 1
            return None
        try:
            if not self._authenticate(device_id, token):
                del self._sessions[device_id]
                return None
            decision = self._policies.validate_device_presentation(
                device_id, claimed_policy_version=session.policy_version,
                now=checked_at.isoformat(),
            )
        except DatabaseError:
            del self._sessions[device_id]
            self._diagnostics["authorization_store_error"] += 1
            return None
        if not decision.allowed or decision.policy_id != session.policy_id:
            del self._sessions[device_id]
            reason = decision.reason if not decision.allowed else "policy_binding_changed"
            self._diagnostics[reason] += 1
            return None
        return session

    def heartbeat(self, device_id: str, session_id: UUID, token: str) -> bool:
        now = self._steady_clock()
        session = self._check_session(device_id, session_id, token, now, self._utc_clock())
        if session is None:
            return False
        session.last_heartbeat = now
        return True

    def take_next(
        self, device_id: str, session_id: UUID, token: str,
    ) -> dict[str, Any] | None:
        """取出一筆待派送意圖，接手後的傳輸與收據由呼叫端管理。"""
        now = self._steady_clock()
        checked_at = self._utc_clock()
        session = self._check_session(device_id, session_id, token, now, checked_at)
        if session is None or (
            now - session.connected_at < self._stable_seconds
            or session.last_heartbeat - session.connected_at < self._stable_seconds
        ):
            return None

        self._expire(checked_at)
        eligible = [
            entry.payload for entry in self._pending.values()
            if entry.payload["device_id"] == device_id
            and entry.payload["policy_version"] == session.policy_version
            and entry.policy_id == session.policy_id
        ]
        if not eligible:
            return None
        oldest = eligible[0]
        highest = max(eligible, key=lambda intent: intent["priority"])
        if highest is oldest or session.consecutive_priority >= self._priority_burst:
            selected = oldest
            session.consecutive_priority = 0
        else:
            selected = highest
            session.consecutive_priority += 1
        del self._pending[selected["delivery_id"]]
        return selected
