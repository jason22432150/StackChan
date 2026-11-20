"""協定解析與白名單驗證。"""

from __future__ import annotations

import pytest

from app.protocol import (
    ProtocolError,
    make_envelope,
    parse_envelope,
    validate_device_inbound,
    validate_push_command,
)


def test_parse_hello_ok():
    raw = {
        "v": 1,
        "id": "msg-1",
        "type": "hello",
        "payload": {"device_id": "sc-001", "mode": "companion", "caps": []},
    }
    env = parse_envelope(raw)
    validate_device_inbound(env)
    assert env.type == "hello"


def test_reject_unknown_version():
    with pytest.raises(ProtocolError) as exc:
        parse_envelope({"v": 99, "id": "x", "type": "hello", "payload": {}})
    assert exc.value.code == "bad_version"


def test_reject_unknown_inbound_type():
    env = make_envelope("shell.exec", {"cmd": "rm -rf /"})
    with pytest.raises(ProtocolError) as exc:
        validate_device_inbound(env)
    assert exc.value.code == "unknown_type"


def test_reject_bad_animation():
    env = make_envelope("animation.play", {"name": "launch_missiles"})
    with pytest.raises(ProtocolError) as exc:
        validate_push_command(env)
    assert exc.value.code == "bad_animation"


def test_accept_safe_motion():
    env = make_envelope("motion.set", {"yaw_deg": 10, "pitch_deg": 5, "speed": 200})
    validate_push_command(env)


def test_reject_overlimit_motion():
    env = make_envelope("motion.set", {"yaw_deg": 90, "pitch_deg": 0, "speed": 200})
    with pytest.raises(ProtocolError) as exc:
        validate_push_command(env)
    assert exc.value.code == "motion_yaw_limit"


def test_reject_long_text():
    env = make_envelope("text.show", {"text": "x" * 200})
    with pytest.raises(ProtocolError) as exc:
        validate_push_command(env)
    assert exc.value.code == "text_too_long"
