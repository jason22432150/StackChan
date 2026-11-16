"""P1-07：單一清單與 CI／PR 規範自檢。"""

from __future__ import annotations

from pathlib import Path

import yaml

from stackchan.contracts.paths import repo_root


def test_single_development_checklist_exists() -> None:
    root = repo_root()
    checklist = root / "docs" / "stackchan-agent-spec" / "docs" / "09_DEVELOPMENT_CHECKLIST.md"
    assert checklist.is_file()
    text = checklist.read_text(encoding="utf-8")
    assert "唯一正式任務追蹤清單" in text or "唯一一份開發任務" in text or "唯一正式" in text

    # 規格包內不得另有平行 DEVELOPMENT_CHECKLIST
    extras = list(
        (root / "docs" / "stackchan-agent-spec").rglob("*DEVELOPMENT_CHECKLIST*")
    )
    assert {path.resolve() for path in extras} == {checklist.resolve()}


def test_ci_workflow_runs_required_pytest_suites() -> None:
    root = repo_root()
    workflow_path = root / ".github" / "workflows" / "agent-contracts.yml"
    assert workflow_path.is_file()
    document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert document["name"] == "Agent contracts"

    job = document["jobs"]["contract-tests"]
    run_steps = [
        step.get("run", "")
        for step in job["steps"]
        if isinstance(step, dict) and "run" in step
    ]
    joined = "\n".join(run_steps)
    assert "uv sync --group dev" in joined
    for suite in (
        "tests/contracts",
        "tests/bridge",
        "tests/coordinator",
        "tests/security",
        "tests/retention",
        "tests/meta",
    ):
        assert suite in joined


def test_ci_pr_norms_document_lists_high_risk_gates() -> None:
    root = repo_root()
    norms = root / "docs" / "stackchan-agent-spec" / "docs" / "12_CI_PR_NORMS.md"
    assert norms.is_file()
    text = norms.read_text(encoding="utf-8")
    assert "09_DEVELOPMENT_CHECKLIST.md" in text
    assert "高風險" in text
    assert "firmware" in text.lower() or "韌體" in text
    assert "127.0.0.1" in text
    assert "人工" in text


def test_workflow_does_not_flash_firmware() -> None:
    root = repo_root()
    text = (root / ".github" / "workflows" / "agent-contracts.yml").read_text(
        encoding="utf-8"
    )
    lowered = text.lower()
    for banned in ("idf.py flash", "esptool", "ota", "burn"):
        assert banned not in lowered
