#!/usr/bin/env python3.13
"""Regression coverage for WP-R6 verification and orchestration baselines."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_fix_helper_scripts_compile() -> None:
    for relative_path in ("scripts/fix_files.py", "scripts/fix_corrupted_files.py"):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        compile(source, relative_path, "exec")


def test_orchestration_baseline_artifacts_exist_with_minimum_shape() -> None:
    session_registry = json.loads(
        (PROJECT_ROOT / "orchestration/session_registry.json").read_text(encoding="utf-8")
    )
    assert session_registry["sessions"] == []
    assert "session_id" in session_registry["session_record_contract"]["required_fields"]

    context_sync_rules = json.loads(
        (PROJECT_ROOT / "orchestration/context_sync_rules.json").read_text(
            encoding="utf-8"
        )
    )
    triggers = {rule["trigger"] for rule in context_sync_rules["sync_rules"]}
    assert {"blueprint_change", "style_guide_change", "bucket_rebuild"} <= triggers

    fallback_routes = json.loads(
        (PROJECT_ROOT / "orchestration/fallback_routes.json").read_text(encoding="utf-8")
    )
    failure_types = {route["failure_type"] for route in fallback_routes["routes"]}
    assert {
        "planner_parse_failure",
        "approval_wait_timeout",
        "state_summary_mismatch",
    } <= failure_types

    next_action_policy = (
        PROJECT_ROOT / "orchestration/next_action_policy.md"
    ).read_text(encoding="utf-8")
    assert "3개 이하" in next_action_policy
    assert "blocking_issues.json" in next_action_policy
    assert "next_actions.json" in next_action_policy
