import json
from datetime import datetime, timedelta, timezone
from sqlite3 import OperationalError

import pytest

from stackchan.contracts.validate import (
    ContractValidationError,
    validate_device_stream_envelope,
    validate_notification_intent,
)
from stackchan.coordinator.device_stream import encode_notification_intent
from stackchan.coordinator.dispatch import NotificationDispatcher
from stackchan.security.auth_bridge import StoreBackedTokenDirectory
from stackchan.security.identity import TokenHasher
from stackchan.security.policy import PolicyService
from stackchan.security.store import SecurityStore


class Clock:
    elapsed = 0.0
    wall = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)

    def advance(self, seconds):
        self.elapsed += seconds
        self.wall += timedelta(seconds=seconds)


def publish(policies, policy_id, *, expires="2099-01-01T00:00:00Z"):
    policies.publish({
        "policy_id": policy_id, "version": "v1", "privacy_mode": "private",
        "valid_until": expires,
    })


@pytest.fixture
def setup_dispatch(tmp_path):
    with SecurityStore(
        tmp_path / "security.sqlite", hasher=TokenHasher(pepper=b"test"),
    ) as store:
        tokens = StoreBackedTokenDirectory(store)
        policies = PolicyService(store)
        publish(policies, "default")
        for device, token, scopes in [
            ("a", "device-a", ["device:stream"]),
            ("a", "other-a", ["device:stream"]),
            ("a", "limited-a", ["device:policy"]),
            ("b", "device-b", ["device:stream"]),
        ]:
            store.upsert_subject(device, "device", device)
            store.issue_grant(
                grant_id=token, subject_id=device, subject_type="device",
                token_plaintext=token, scopes=scopes, expires_at="2099-01-01T00:00:00Z",
            )
            policies.bind_device(device, "default", "v1")
        clock = Clock()
        dispatcher = NotificationDispatcher(
            tokens, policies, stable_seconds=5, heartbeat_timeout=4, capacity=5,
            priority_burst=2, steady_clock=lambda: clock.elapsed, utc_clock=lambda: clock.wall,
        )
        yield dispatcher, clock, tokens, policies


def intent(delivery_id, *, device="a", priority=10, expires="2026-11-16T12:01:00Z"):
    return {
        "schema_version": "0.1", "notification_id": delivery_id,
        "delivery_id": delivery_id, "device_id": device, "event_ids": ["event-private"],
        "priority": priority, "policy_version": "v1", "generation": 1,
        "expires_at": expires,
        "presentation_policy": {"ui": True, "audio": False, "motion": False, "tts": False},
    }


def stabilize(dispatcher, clock, device, session, token):
    assert session is not None
    for seconds in (3, 2):
        clock.advance(seconds)
        assert dispatcher.heartbeat(device, session, token)


def test_authenticated_dispatch_can_encode_a_device_frame(setup_dispatch):
    dispatcher, clock, _, _ = setup_dispatch
    assert dispatcher.enqueue(intent("for-a", device="a"))
    assert dispatcher.enqueue(intent("for-b", device="b", priority=100))
    session = dispatcher.connect("a", "device-a", "v1")
    stabilize(dispatcher, clock, "a", session, "device-a")

    selected = dispatcher.take_next("a", session, "device-a")
    assert selected is not None
    frame = validate_device_stream_envelope(json.loads(encode_notification_intent(selected, sent_at=clock.wall)))
    payload = validate_notification_intent(frame["payload"])
    assert frame["type"] == "notification.intent"
    for field in ("device_id", "delivery_id", "policy_version", "generation"):
        assert frame[field] == payload[field] == selected[field]
    assert frame["delivery_id"] == "for-a"


def test_priority_fifo_fairness_and_device_isolation(setup_dispatch):
    dispatcher, clock, _, _ = setup_dispatch
    for payload in (
        intent("old"), intent("urgent-1", priority=100), intent("urgent-2", priority=100),
        intent("urgent-3", priority=100), intent("other-device", device="b", priority=100),
    ):
        assert dispatcher.enqueue(payload)
    session = dispatcher.connect("a", "device-a", "v1")
    stabilize(dispatcher, clock, "a", session, "device-a")
    for expected in ("urgent-1", "urgent-2", "old", "urgent-3"):
        assert dispatcher.take_next("a", session, "device-a")["delivery_id"] == expected
    assert dispatcher.take_next("a", session, "device-a") is None

    other = dispatcher.connect("b", "device-b", "v1")
    stabilize(dispatcher, clock, "b", other, "device-b")
    assert dispatcher.take_next("b", other, "device-b")["delivery_id"] == "other-device"


def test_expiry_at_dispatch_and_queue_backpressure(setup_dispatch):
    dispatcher, clock, _, _ = setup_dispatch
    assert not dispatcher.enqueue(intent("already-old", expires="2026-11-16T13:00:00+01:00"))
    payload = intent("soon", expires="2026-11-16t12:00:05z")
    assert dispatcher.enqueue(payload)
    assert not dispatcher.enqueue(payload)
    for index in range(4):
        assert dispatcher.enqueue(intent(f"item-{index}"))
    assert not dispatcher.enqueue(intent("overflow"))
    with pytest.raises(ContractValidationError):
        dispatcher.enqueue({"device_id": "a"})
    session = dispatcher.connect("a", "device-a", "v1")
    stabilize(dispatcher, clock, "a", session, "device-a")
    assert dispatcher.take_next("a", session, "device-a")["delivery_id"] == "item-0"
    assert dispatcher.enqueue(intent("overflow"))
    assert dispatcher.diagnostics() == {
        "intent_expired": 2, "duplicate_pending_delivery": 1, "queue_full": 1,
    }


def test_disconnect_timeout_and_reconnect_require_fresh_stability(setup_dispatch):
    dispatcher, clock, _, _ = setup_dispatch
    assert dispatcher.enqueue(intent("pending"))
    first = dispatcher.connect("a", "device-a", "v1")
    assert dispatcher.take_next("a", first, "device-a") is None
    stabilize(dispatcher, clock, "a", first, "device-a")
    dispatcher.disconnect("a", first)
    assert dispatcher.take_next("a", first, "device-a") is None

    second = dispatcher.connect("a", "device-a", "v1")
    clock.advance(4)
    assert not dispatcher.heartbeat("a", second, "device-a")
    assert dispatcher.take_next("a", second, "device-a") is None

    third = dispatcher.connect("a", "device-a", "v1")
    clock.advance(3)
    assert dispatcher.heartbeat("a", third, "device-a")
    clock.advance(2)
    assert dispatcher.take_next("a", third, "device-a") is None
    assert dispatcher.heartbeat("a", third, "device-a")
    dispatcher.disconnect("a", second)
    assert dispatcher.take_next("a", third, "device-a")["delivery_id"] == "pending"
    assert dispatcher.diagnostics()["heartbeat_timeout"] == 1


def test_identity_scope_and_grant_revocation_are_checked_on_dispatch(setup_dispatch):
    dispatcher, clock, tokens, _ = setup_dispatch
    assert dispatcher.connect("a", "device-b", "v1") is None
    assert dispatcher.connect("a", "limited-a", "v1") is None
    assert dispatcher.enqueue(intent("pending"))
    session = dispatcher.connect("a", "device-a", "v1")
    stabilize(dispatcher, clock, "a", session, "device-a")
    tokens.revoke("device-a")
    assert dispatcher.take_next("a", session, "other-a") is None
    assert dispatcher.take_next("a", session, "device-a") is None
    replacement = dispatcher.connect("a", "other-a", "v1")
    assert dispatcher.take_next("a", replacement, "other-a") is None
    assert dispatcher.diagnostics() == {"device_unauthorized": 4}


def test_authorization_store_error_requires_reconnect(setup_dispatch, monkeypatch):
    dispatcher, clock, tokens, _ = setup_dispatch
    assert dispatcher.enqueue(intent("pending"))
    session = dispatcher.connect("a", "device-a", "v1")
    stabilize(dispatcher, clock, "a", session, "device-a")

    def unavailable(_token):
        raise OperationalError("private database path")

    with monkeypatch.context() as patch:
        patch.setattr(tokens, "resolve", unavailable)
        assert dispatcher.take_next("a", session, "device-a") is None
    assert dispatcher.diagnostics() == {"authorization_store_error": 1}
    assert not dispatcher.heartbeat("a", session, "device-a")
    replacement = dispatcher.connect("a", "device-a", "v1")
    stabilize(dispatcher, clock, "a", replacement, "device-a")
    assert dispatcher.take_next("a", replacement, "device-a")["delivery_id"] == "pending"


def test_policy_revocation_and_rebinding_with_same_version(setup_dispatch):
    dispatcher, clock, _, policies = setup_dispatch
    assert dispatcher.connect("a", "device-a", "old") is None
    assert dispatcher.enqueue(intent("original-policy"))
    session = dispatcher.connect("a", "device-a", "v1")
    stabilize(dispatcher, clock, "a", session, "device-a")
    policies.revoke("default", "v1")
    assert dispatcher.take_next("a", session, "device-a") is None
    assert dispatcher.connect("a", "device-a", "v1") is None

    publish(policies, "replacement")
    policies.bind_device("a", "replacement", "v1")
    replacement = dispatcher.connect("a", "device-a", "v1")
    stabilize(dispatcher, clock, "a", replacement, "device-a")
    assert dispatcher.take_next("a", replacement, "device-a") is None
    assert dispatcher.enqueue(intent("replacement-policy"))
    assert dispatcher.take_next("a", replacement, "device-a")["delivery_id"] == "replacement-policy"


@pytest.mark.parametrize("expiration", ["2026-11-16T13:00:05+01:00", "invalid"])
def test_policy_expiry_or_invalid_timestamp_fail_closed(setup_dispatch, expiration):
    dispatcher, clock, _, policies = setup_dispatch
    publish(policies, "short", expires=expiration)
    policies.bind_device("a", "short", "v1")
    session = dispatcher.connect("a", "device-a", "v1")
    if expiration == "invalid":
        assert session is None
        assert dispatcher.diagnostics() == {"policy_time_invalid": 1}
        return
    assert dispatcher.enqueue(intent("expires-policy-first"))
    clock.advance(3)
    assert dispatcher.heartbeat("a", session, "device-a")
    clock.advance(2)
    assert not dispatcher.heartbeat("a", session, "device-a")
    assert dispatcher.diagnostics() == {"policy_expired": 1}
