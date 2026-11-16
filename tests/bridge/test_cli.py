"""P2-01：Bridge CLI 基本執行。"""

from __future__ import annotations

import json
from pathlib import Path

from stackchan import main as stackchan_main
from stackchan.bridge.cli import main as bridge_main


def test_stackchan_bridge_init_status_ingest(tmp_path: Path, capsys) -> None:
    db = tmp_path / "bridge.sqlite3"
    payload = tmp_path / "hook.json"
    payload.write_text(
        json.dumps(
            {
                "type": "agent-turn-complete",
                "thread-id": "cli-thread",
                "turn-id": "cli-turn",
                "cwd": "F:/project",
                "client": "codex-tui",
            }
        ),
        encoding="utf-8",
    )

    assert (
        bridge_main(
            ["init", "--db", str(db), "--bridge-id", "bridge_cli_1", "--epoch", "epoch-1"]
        )
        == 0
    )
    init_out = json.loads(capsys.readouterr().out)
    assert init_out["ok"] is True
    assert init_out["settings"]["bridge_id"] == "bridge_cli_1"

    assert (
        bridge_main(
            [
                "ingest-hook",
                "--db",
                str(db),
                "--bridge-id",
                "bridge_cli_1",
                "--adapter",
                "codex",
                "--file",
                str(payload),
            ]
        )
        == 0
    )
    ingest_out = json.loads(capsys.readouterr().out)
    assert ingest_out["ok"] is True
    assert ingest_out["created"] is True
    assert ingest_out["event_type"] == "response.completed"
    assert ingest_out["evidence_level"] == "observed"

    assert bridge_main(["status", "--db", str(db), "--bridge-id", "bridge_cli_1"]) == 0
    status_out = json.loads(capsys.readouterr().out)
    assert status_out["pending_count"] == 1
    assert status_out["next_sequence"] == 2


def test_stackchan_top_level_dispatches_bridge(tmp_path: Path, capsys) -> None:
    db = tmp_path / "b.sqlite3"
    try:
        stackchan_main(
            ["bridge", "init", "--db", str(db), "--bridge-id", "bridge_top"]
        )
    except SystemExit as exc:
        assert exc.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["settings"]["bridge_id"] == "bridge_top"


def test_adapters_list(capsys) -> None:
    assert bridge_main(["adapters"]) == 0
    text = capsys.readouterr().out
    assert "codex.hooks" in text
    assert "cursor.hooks" in text


def test_cursor_argv_style_via_file(tmp_path: Path, capsys) -> None:
    db = tmp_path / "bridge.sqlite3"
    payload = tmp_path / "cursor-stop.json"
    payload.write_text(
        json.dumps(
            {
                "hook_event_name": "stop",
                "conversation_id": "c-cli",
                "generation_id": "g-cli",
                "status": "completed",
                "loop_count": 0,
            }
        ),
        encoding="utf-8",
    )
    bridge_main(["init", "--db", str(db), "--bridge-id", "b1"])
    capsys.readouterr()
    code = bridge_main(
        [
            "ingest-hook",
            "--db",
            str(db),
            "--bridge-id",
            "b1",
            "--adapter",
            "cursor",
            "--file",
            str(payload),
        ]
    )
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["event_type"] == "response.completed"
