#!/usr/bin/env python3
"""
init_workspace.py — 프로젝트 워크스페이스 디렉토리 구조 생성

Usage:
    python scripts/init_workspace.py PRJ-2024-ABC-001

Creates the full directory structure defined in CLAUDE.md for a new project.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

WORKSPACE_STRUCTURE = [
    "00_definition",
    "01_raw",
    "02_file_registry",
    "03_normalized_md",
    "04_segments",
    "05_planning",
    "06_buckets",
    "07_drafts",
    "08_review",
    "09_handoff",
    "10_evidence_pack",
    "guidance",
    "context_bus",
]

SEGMENTS_DIR = "04_segments"

DEFAULT_NOW = "2026-04-02T00:00:00Z"


def _make_initial_json(project_id: str, phase: str = "P0") -> dict:
    """Return valid initial JSON for top-level state files."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "project_id": project_id,
        "current_phase": phase,
        "created_at": now,
        "updated_at": now,
    }


def _write_json_file(path: Path, data: dict) -> None:
    """Write a JSON file with proper formatting."""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _copy_guidance_files(workspace_path: Path) -> list[Path]:
    """Copy guidance files from root guidance/ to workspace guidance/."""
    root_guidance = Path(__file__).parent.parent / "guidance"
    workspace_guidance = workspace_path / "guidance"

    copied_files: list[Path] = []
    if not root_guidance.exists():
        print(f"  Warning: Root guidance directory not found: {root_guidance}")
        return copied_files

    for guidance_file in root_guidance.iterdir():
        if guidance_file.is_file():
            dest = workspace_guidance / guidance_file.name
            shutil.copy2(guidance_file, dest)
            copied_files.append(dest)
            print(f"  Copied: {dest}")

    return copied_files


def create_workspace(project_id: str, base_path: Path | None = None) -> Path:
    """Create a complete workspace directory structure for a project."""
    if not project_id.startswith("PRJ-"):
        raise ValueError(f"Invalid project_id format: {project_id}. Expected PRJ-YYYY-CODE-NNN")

    if base_path is None:
        base_path = Path("workspaces") / project_id
    else:
        base_path = base_path / project_id

    if base_path.exists():
        raise FileExistsError(f"Workspace already exists: {base_path}")

    created_dirs: list[Path] = []

    for subdir in WORKSPACE_STRUCTURE:
        dir_path = base_path / subdir
        dir_path.mkdir(parents=True, exist_ok=False)
        created_dirs.append(dir_path)
        print(f"  Created: {dir_path}")

    # Copy guidance files from root guidance/ to workspace guidance/
    print("\n  Copying guidance files:")
    copied_guidance = _copy_guidance_files(base_path)
    if not copied_guidance:
        print("  No guidance files to copy")

    # Create top-level state files with valid initial JSON
    project_state = _make_initial_json(project_id, "P0")
    project_state["sections"] = {}
    _write_json_file(base_path / "project_state.json", project_state)

    blocking_issues = _make_initial_json(project_id)
    blocking_issues["issues"] = []
    _write_json_file(base_path / "blocking_issues.json", blocking_issues)

    next_actions = _make_initial_json(project_id)
    next_actions["actions"] = []
    next_actions["proposed"] = []
    _write_json_file(base_path / "next_actions.json", next_actions)

    draft_queries = _make_initial_json(project_id)
    draft_queries["queries"] = []
    _write_json_file(base_path / "draft_queries.json", draft_queries)

    approval_gates = _make_initial_json(project_id)
    approval_gates["gates"] = {}
    _write_json_file(base_path / "approval_gates.json", approval_gates)

    manual_overrides = _make_initial_json(project_id)
    manual_overrides["overrides"] = []
    _write_json_file(base_path / "manual_overrides.json", manual_overrides)

    for filename in (
        "project_state.json",
        "blocking_issues.json",
        "next_actions.json",
        "draft_queries.json",
        "approval_gates.json",
        "manual_overrides.json",
    ):
        print(f"  Created: {base_path / filename}")

    # Create P0 definition files (project_charter, stakeholder_matrix)
    charter_data = {
        "project_id": project_id,
        "project_title": f"ESG Report for {project_id}",
        "reporting_entity": "TBD",
        "reporting_period": {"start": "TBD", "end": "TBD"},
        "framework": ["GRI"],
        "scope": {"consolidation": "standalone", "boundary": "corporate"},
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "draft",
    }
    _write_json_file(base_path / "00_definition" / "project_charter.json", charter_data)
    print(f"  Created: {base_path / '00_definition' / 'project_charter.json'}")

    stakeholder_data = {
        "project_id": project_id,
        "stakeholders": [],
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _write_json_file(base_path / "00_definition" / "stakeholder_matrix.json", stakeholder_data)
    print(f"  Created: {base_path / '00_definition' / 'stakeholder_matrix.json'}")

    # Create segment counter initial file
    next_seg_path = base_path / "04_segments" / "next_segment_id.json"
    _write_json_file(next_seg_path, {"next_id": 1})
    print(f"  Created: {next_seg_path}")

    print(f"\nWorkspace created successfully: {base_path}")
    return base_path


@click.command()
@click.argument("project_id")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Base path for workspaces directory (default: ./workspaces)",
)
def main(project_id: str, base_path: Path | None) -> int:
    """Initialize a new project workspace directory structure."""
    try:
        create_workspace(project_id, base_path)
        return 0
    except (ValueError, FileExistsError) as e:
        click.echo(f"Error: {e}", err=True)
        return 1
    except OSError as e:
        click.echo(f"OS Error: {e}", err=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
