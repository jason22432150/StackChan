"""個人版 Codex Bridge：隱私、pending 摘要、Codex 設定輸出。"""

from __future__ import annotations

import json
from pathlib import Path

from stackchan.adapters import CodexAdapter
from stackchan.bridge.cli import main as bridge_main
from stackchan.bridge.paths import default_bridge_db_path, default_bridge_id
from stackchan.bridge.service import BridgeService
from stackchan.bridge.store import BridgeStore


def test_default_paths_prefer_env(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / "custom-bridge.sqlite3"
    monkeypatch.setenv("STACKCHAN_BRIDGE_DB", str(db))
    monkeypatch.setenv("STACKCHAN_BRIDGE_ID", "bridge_from_env")
    assert default_bridge_db_path() == db
    assert default_bridge_id() == "bridge_from_env"


def test_outbox_strips_prompt_and_assistant_message(tmp_path: Path) -> None:
    store = BridgeStore(tmp_path / "bridge.sqlite3")
    store.ensure_bridge("bridge_primary", epoch="epoch-1")
    service = BridgeService(store, "bridge_primary")
    outcome = service.ingest_raw(
        CodexAdapter(),
        {
            "type": "agent-turn-complete",
            "thread-id": "th-secret",
            "turn-id": "tu-secret",
            "cwd": "/Users/me/project",
            "client": "codex-tui",
            "input-messages": ["請把 API_KEY=sk-live-xxx 寫進程式"],
            "last-assistant-message": "已完成，密碼是 hunter2",
            "api_key": "should-never-appear",
            "password": "hunter2",
        },
    )
    assert outcome.result is not None
    assert outcome.event is not None
    blob = json.dumps(outcome.event, ensure_ascii=False)
    assert "sk-live-xxx" not in blob
    assert "hunter2" not in blob
    assert "input-messages" not in blob
    assert "last-assistant-message" not in blob
    assert "api_key" not in outcome.event.get("source_payload", {})
    assert "password" not in outcome.event.get("source_payload", {})
    assert service.status()["delivers_to_cores3"] is False
    assert service.status()["delivers_to_coordinator"] is False
    store.close()


def test_pending_cli_lists_summary_without_payload(tmp_path: Path, capsys) -> None:
    db = tmp_path / "bridge.sqlite3"
    assert bridge_main(["init", "--db", str(db), "--bridge-id", "bridge_primary"]) == 0
    capsys.readouterr()

    payload = tmp_path / "hook.json"
    payload.write_text(
        json.dumps(
            {
                "hook_event_name": "Stop",
                "session_id": "sess-p",
                "turn_id": "turn-p",
                "cwd": "/tmp/demo",
                "last_assistant_message": "secret body",
            }
        ),
        encoding="utf-8",
    )
    assert (
        bridge_main(
            [
                "ingest-hook",
                "--db",
                str(db),
                "--bridge-id",
                "bridge_primary",
                "--adapter",
                "codex",
                "--file",
                str(payload),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert bridge_main(["pending", "--db", str(db), "--bridge-id", "bridge_primary"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["pending_count"] == 1
    assert out["pending"][0]["event_type"] == "response.completed"
    assert out["pending"][0]["evidence_level"] == "observed"
    assert "source_payload" not in out["pending"][0]
    assert "secret body" not in json.dumps(out, ensure_ascii=False)


def test_print_codex_setup_does_not_write_home_codex(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    db = tmp_path / "bridge.sqlite3"
    assert (
        bridge_main(
            [
                "print-codex-setup",
                "--db",
                str(db),
                "--bridge-id",
                "bridge_primary",
                "--stackchan-bin",
                "stackchan",
            ]
        )
        == 0
    )
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert "hooks_json" in out
    assert out["hooks_json"]["hooks"]["Stop"]
    assert "ingest-hook" in out["hooks_json"]["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert not (fake_home / ".codex").exists()


def test_deploy_bridge_wrappers_exist_and_are_executable() -> None:
    root = Path(__file__).resolve().parents[2]
    for name in ("codex-hook.sh", "codex-notify.sh"):
        path = root / "deploy" / "bridge" / name
        assert path.is_file()
        assert path.stat().st_mode & 0o111
    example = root / "deploy" / "bridge" / "hooks.json.example"
    assert "Stop" in example.read_text(encoding="utf-8")
