#!/usr/bin/env python3.13
"""
Basic CLI smoke tests that do not require API keys or external services.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from llm.cli import main


def test_cli_help_invokes_successfully() -> None:
    """Root CLI help should render without external dependencies."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "sustainreport AI" in result.output
    assert "init-workspace" in result.output
    assert "run-plan" in result.output


def test_cli_registers_core_commands() -> None:
    """The main Click group should expose the core workflow commands."""
    expected = {
        "approve",
        "check-gate",
        "init-workspace",
        "run-draft",
        "run-ingestion",
        "run-pipeline",
        "run-plan",
        "status",
        "update-state",
    }

    assert expected.issubset(set(main.commands))


def test_init_workspace_creates_expected_structure(tmp_path: Path) -> None:
    """init-workspace should create a safe local workspace in a temp directory."""
    runner = CliRunner()
    project_id = "PRJ-2026-OSS-001"

    result = runner.invoke(main, ["init-workspace", project_id, "--base-path", str(tmp_path)])

    workspace = tmp_path / project_id
    assert result.exit_code == 0
    assert workspace.exists()
    assert (workspace / "05_planning").is_dir()
    assert (workspace / "guidance" / "style_guide.json").exists()
    assert (workspace / "project_state.json").exists()
