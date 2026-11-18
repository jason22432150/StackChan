"""Local pairing lookup must remain read-only, bounded and free of credential output."""

from __future__ import annotations

import json

import pytest

from stackchan.coordinator import cli
from stackchan.security.identity import TokenHasher
from stackchan.security.store import SecurityStore


@pytest.fixture
def lookup_db(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKCHAN_SECURITY_PEPPER", "lookup-test-pepper")
    path = tmp_path / "pairing # lookup.sqlite"
    with SecurityStore(path, hasher=TokenHasher(b"lookup-test-pepper")) as store:
        for index, (subject, status, expires, code) in enumerate([
            ("device", "pending", "2099-01-01T00:00:00Z", "ABC123"),
            ("device", "approved", "2099-01-01T00:00:00Z", "ABC123"),
            ("device", "pending", "2000-01-01T00:00:00Z", "ABC123"),
            ("device", "rejected", "2099-01-01T00:00:00Z", "ABC123"),
            ("device", "completed", "2099-01-01T00:00:00Z", "ABC123"),
            ("bridge", "pending", "2099-01-01T00:00:00Z", "ABC123"),
            ("device", "pending", "2099-01-01T00:00:00Z", "OTHER1"),
        ]):
            pairing_id = f"pair_{index:016x}"
            store.create_pairing_session(
                pairing_id=pairing_id, subject_type=subject, display_name="CoreS3\x1b[31m\n",
                user_code=code, expires_at=expires,
            )
            store.set_pairing_status(pairing_id, status)
    monkeypatch.setattr("http.client.HTTPSConnection", lambda *a, **k: pytest.fail("lookup must not open a connection"))
    monkeypatch.setattr(SecurityStore, "initialize_schema", lambda *a: pytest.fail("lookup must not initialize schema"))
    return path


def test_lookup_returns_only_matching_unexpired_device_metadata(lookup_db, capsys):
    before = lookup_db.read_bytes()
    assert cli.main(["find-pairings", "--security-db", str(lookup_db), "--user-code", "ABC123"]) == 0
    output = capsys.readouterr()
    assert not output.err and "\x1b" not in output.out and "ABC123" not in output.out
    result = json.loads(output.out)
    assert result["truncated"] is False
    assert [row["pairing_id"] for row in result["pairings"]] == ["pair_0000000000000000", "pair_0000000000000001"]
    assert [row["status"] for row in result["pairings"]] == ["pending", "approved"]
    assert all(set(row) == {"pairing_id", "display_name", "status", "expires_at"} for row in result["pairings"])
    assert lookup_db.read_bytes() == before


@pytest.mark.parametrize("problem", ["wrong-code", "wrong-pepper"])
def test_lookup_has_no_fallback_when_code_or_pepper_does_not_match(lookup_db, monkeypatch, capsys, problem):
    if problem == "wrong-pepper":
        monkeypatch.setenv("STACKCHAN_SECURITY_PEPPER", "different-pepper")
    assert cli.main(["find-pairings", "--security-db", str(lookup_db), "--user-code",
                     "ZZZZZZ" if problem == "wrong-code" else "ABC123"]) == 0
    assert json.loads(capsys.readouterr().out) == {"pairings": [], "truncated": False}


@pytest.mark.parametrize("problem", ["no-pepper", "bad-code", "approve", "host"])
def test_lookup_rejects_invalid_options_before_opening_database(tmp_path, monkeypatch, problem):
    path = tmp_path / "missing.sqlite"
    monkeypatch.setenv("STACKCHAN_SECURITY_PEPPER", "test-pepper")
    if problem == "no-pepper":
        monkeypatch.delenv("STACKCHAN_SECURITY_PEPPER")
    args = ["find-pairings", "--security-db", str(path), "--user-code", "abc" if problem == "bad-code" else "ABC123"]
    args += {"approve": ["--approve"], "host": ["--host", "192.168.1.10"]}.get(problem, [])
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2 and not path.exists()


@pytest.mark.parametrize("kind", ["missing", "empty"])
def test_lookup_never_creates_or_migrates_a_database(tmp_path, monkeypatch, capsys, kind):
    monkeypatch.setenv("STACKCHAN_SECURITY_PEPPER", "test-pepper")
    path = tmp_path / "uninitialized.sqlite"
    if kind == "empty":
        path.write_bytes(b"")
    assert cli.main(["find-pairings", "--security-db", str(path), "--user-code", "ABC123"]) == 1
    assert "existing security database" in capsys.readouterr().err
    assert path.read_bytes() == b"" if kind == "empty" else not path.exists()


def test_lookup_reports_truncation_without_selecting_a_candidate(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("STACKCHAN_SECURITY_PEPPER", "lookup-test-pepper")
    path = tmp_path / "many.sqlite"
    with SecurityStore(path, hasher=TokenHasher(b"lookup-test-pepper")) as store:
        for index in range(33):
            store.create_pairing_session(
                pairing_id=f"pair_{index:016x}", subject_type="device", display_name="CoreS3",
                user_code="ABC123", expires_at="2099-01-01T00:00:00Z",
            )
    assert cli.main(["find-pairings", "--security-db", str(path), "--user-code", "ABC123"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["truncated"] is True and len(result["pairings"]) == 32
    with SecurityStore(path, hasher=TokenHasher(b"lookup-test-pepper"), read_only=True) as store:
        assert store.get_pairing("pair_0000000000000000")["status"] == "pending"
