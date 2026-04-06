#!/usr/bin/env python3.13
"""Repair sample workspace files that were wrapped with edit-tool artifacts."""

from __future__ import annotations

import json
from pathlib import Path


PATH_HEADER_PREFIXES = ("sustainreport_ai/", "/Users/", "/home/", "workspaces/")


def _is_path_header(line: str) -> bool:
    return line.strip().startswith(PATH_HEADER_PREFIXES)


def _is_fence(line: str) -> bool:
    return line.strip().startswith("```")


def _strip_edit_artifacts(content: str) -> str:
    lines = content.splitlines()
    cleaned_lines: list[str] = []

    for index, line in enumerate(lines):
        stripped = line.strip()

        if index == 0 and (_is_path_header(line) or _is_fence(line)):
            continue
        if not cleaned_lines and not stripped:
            continue
        if _is_path_header(line) or _is_fence(line):
            continue

        cleaned_lines.append(line)

    if not cleaned_lines:
        return ""

    return "\n".join(cleaned_lines).rstrip() + "\n"


def fix_file(path: Path) -> bool:
    """Remove known edit-tool artifacts from a single file in place."""
    if not path.exists():
        print(f"  SKIP: {path.name} (not found)")
        return False

    original = path.read_text(encoding="utf-8")
    cleaned = _strip_edit_artifacts(original)

    if not cleaned or cleaned == original:
        print(f"  OK: {path.name} (no fix needed)")
        return False

    print(f"  FIXING: {path.name}")
    path.write_text(cleaned, encoding="utf-8")
    return True


def validate_json_files(workspace: Path) -> tuple[int, int]:
    """Return the number of valid and invalid JSON files in a workspace."""
    passed = 0
    failed = 0

    for json_file in workspace.rglob("*.json"):
        try:
            json.loads(json_file.read_text(encoding="utf-8"))
            print(f"  OK: {json_file.relative_to(workspace)}")
            passed += 1
        except json.JSONDecodeError as exc:
            print(f"  FAIL: {json_file.relative_to(workspace)} - {exc}")
            failed += 1

    return passed, failed


def main() -> None:
    workspace = Path("workspaces/PRJ-2026-TST-003")
    targets = [
        workspace / "00_definition" / "project_charter.json",
        workspace / "01_raw" / "test_report.txt",
        workspace / "03_normalized_md" / "F-0001.md",
        workspace / "06_buckets" / "framework_index.json",
        workspace / "06_buckets" / "SEC-3.1.json",
        workspace / "07_drafts" / "SEC-2.md",
    ]

    print("=== Corrupted Files Fix ===")
    for target in targets:
        fix_file(target)

    print("\n=== Validation ===")
    passed, failed = validate_json_files(workspace)

    print("\n=== Summary ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    main()
