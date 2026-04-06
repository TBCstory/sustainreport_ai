#!/usr/bin/env python3.13
"""
WP-R5 regression tests for live state and gate consistency.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from click.testing import CliRunner

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def copy_sample_workspace(tmp_path: Path) -> Path:
    """Copy the inconsistent sample workspace into a temp location."""
    source = PROJECT_ROOT / "workspaces" / "PRJ-2026-TST-003"
    workspace = tmp_path / "state-workspace"
    shutil.copytree(source, workspace)
    return workspace


def test_status_and_dry_run_follow_live_phase_story(tmp_path) -> None:
    """status/dry-run should report the earliest incomplete phase story."""
    from llm.cli import cmd_check_gate, cmd_run_pipeline, cmd_status
    from scripts.update_project_state import build_project_state_snapshot

    workspace = copy_sample_workspace(tmp_path)
    state = build_project_state_snapshot(workspace)

    assert state["current_phase"] == "P3"
    assert state["phase_status"]["P2"] == "complete"
    assert state["phase_status"]["P3"] == "in_progress"
    assert state["phase_status"]["P6"] == "pending"

    runner = CliRunner()

    status = runner.invoke(cmd_status, ["--workspace", str(workspace)])
    assert status.exit_code == 0, status.output
    assert "Phase P3" in status.output

    dry_run = runner.invoke(cmd_run_pipeline, ["--workspace", str(workspace), "--dry-run"])
    assert dry_run.exit_code == 0, dry_run.output
    assert "Current phase: P3" in dry_run.output
    assert "P3_to_P4: blocked" in dry_run.output
    assert "P5_to_P6" not in dry_run.output

    check_gate = runner.invoke(cmd_check_gate, ["P2_to_P3", "--workspace", str(workspace)])
    assert check_gate.exit_code == 0, check_gate.output
    assert '"result": "passed"' in check_gate.output


def test_rebuild_next_actions_keeps_query_and_issue_ids_unique(tmp_path) -> None:
    """Each open query/issue should keep its own action identity."""
    from scripts.rebuild_summaries import rebuild_blocking_issues, rebuild_next_actions

    workspace = copy_sample_workspace(tmp_path)
    blocking = rebuild_blocking_issues(workspace)
    next_actions = rebuild_next_actions(workspace, blocking["issues"])

    actions = next_actions["actions"]
    action_ids = [action["action_id"] for action in actions]

    assert len(action_ids) == len(set(action_ids))
    assert len({action["query_id"] for action in actions if action.get("query_id")}) == 3
    assert len({action["issue_id"] for action in actions if action.get("issue_id")}) == 7


def test_generate_narrative_status_od7(tmp_path) -> None:
    """OD-7: generate_narrative_status produces natural-language status for AI sessions."""
    from scripts.update_project_state import generate_narrative_status

    workspace = copy_sample_workspace(tmp_path)
    narrative = generate_narrative_status(workspace)

    # Should contain key narrative elements
    assert "프로젝트" in narrative
    assert "Phase P3" in narrative
    assert "버킷 구축" in narrative
    # Should show blockers
    assert "차단 요인" in narrative
    # Should show open queries
    assert "미해결 질의" in narrative
    # Should show next actions
    assert "다음 행동" in narrative
    # Should be <= 3 next actions
    assert narrative.count("\n    [") <= 12  # 3 blockers + 3 queries + 3 actions + 3 headers = 12
