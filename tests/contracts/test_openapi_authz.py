"""OpenAPI 路由 scope 與未授權拒絕測試。"""

from __future__ import annotations

import pytest

from stackchan.contracts import (
    ApiGate,
    AuthorizationError,
    Principal,
    TokenDirectory,
    find_route,
    load_route_requirements,
)


@pytest.fixture
def tokens() -> TokenDirectory:
    directory = TokenDirectory()
    directory.issue(
        "bridge-token",
        Principal("bridge_1", "bridge", frozenset({"bridge:write", "bridge:sync"})),
    )
    directory.issue(
        "device-token",
        Principal(
            "cores3_1",
            "device",
            frozenset({"device:policy", "device:receipt", "device:stream"}),
        ),
    )
    directory.issue(
        "dashboard-token",
        Principal("user_1", "dashboard", frozenset({"dashboard:read", "read:write"})),
    )
    directory.issue(
        "admin-token",
        Principal("admin_1", "dashboard", frozenset({"admin:pairing", "admin:health"})),
    )
    directory.issue(
        "revoked-token",
        Principal("bridge_x", "bridge", frozenset({"bridge:write"}), revoked=True),
    )
    return directory


@pytest.fixture
def gate(tokens: TokenDirectory) -> ApiGate:
    return ApiGate(tokens)


def test_openapi_routes_declare_required_scopes() -> None:
    routes = load_route_requirements()
    assert len(routes) >= 12
    batch = find_route("POST", "/v1/events/batch")
    assert batch is not None
    assert batch.required_scopes == frozenset({"bridge:write"})
    stream = find_route("GET", "/v1/device-stream")
    assert stream is not None
    assert stream.required_scopes == frozenset({"device:stream"})


def test_missing_authorization_is_unauthorized(gate: ApiGate) -> None:
    with pytest.raises(AuthorizationError) as exc:
        gate.authorize("POST", "/v1/events/batch", None)
    assert exc.value.http_status == 401
    assert exc.value.code == "unauthorized"


def test_invalid_bearer_format_is_unauthorized(gate: ApiGate) -> None:
    with pytest.raises(AuthorizationError) as exc:
        gate.authorize("GET", "/v1/events", "Token abc")
    assert exc.value.http_status == 401


def test_wrong_scope_cannot_read_or_write(gate: ApiGate) -> None:
    # Bridge token must not read dashboard events
    with pytest.raises(AuthorizationError) as exc:
        gate.authorize("GET", "/v1/events", "Bearer bridge-token")
    assert exc.value.http_status == 403
    assert exc.value.code == "forbidden"

    # Dashboard token must not submit bridge batches
    with pytest.raises(AuthorizationError) as exc2:
        gate.authorize("POST", "/v1/events/batch", "Bearer dashboard-token")
    assert exc2.value.http_status == 403


def test_device_cannot_use_bridge_write(gate: ApiGate) -> None:
    with pytest.raises(AuthorizationError) as exc:
        gate.authorize("POST", "/v1/events/batch", "Bearer device-token")
    assert exc.value.http_status == 403


def test_authorized_bridge_and_device_pass(gate: ApiGate) -> None:
    bridge = gate.authorize("POST", "/v1/events/batch", "Bearer bridge-token")
    assert bridge is not None
    assert bridge.subject_type == "bridge"

    device = gate.authorize("GET", "/v1/device-stream", "Bearer device-token")
    assert device is not None
    assert "device:stream" in device.scopes

    receipt = gate.authorize(
        "POST",
        "/v1/deliveries/dlv_1/receipts",
        "Bearer device-token",
    )
    assert receipt is not None


def test_revoked_token_forbidden(gate: ApiGate) -> None:
    with pytest.raises(AuthorizationError) as exc:
        gate.authorize("POST", "/v1/events/batch", "Bearer revoked-token")
    assert exc.value.http_status == 403
    assert exc.value.code == "revoked"


def test_pairing_start_allows_anonymous(gate: ApiGate) -> None:
    principal = gate.authorize("POST", "/v1/pairing/sessions", None)
    assert principal is None


def test_pairing_confirm_requires_admin_scope(gate: ApiGate) -> None:
    with pytest.raises(AuthorizationError):
        gate.authorize(
            "POST",
            "/v1/pairing/sessions/p1/confirm",
            "Bearer dashboard-token",
        )
    admin = gate.authorize(
        "POST",
        "/v1/pairing/sessions/p1/confirm",
        "Bearer admin-token",
    )
    assert admin is not None
