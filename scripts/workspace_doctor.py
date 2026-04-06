#!/usr/bin/env python3.13
"""
scripts/workspace_doctor.py

Workspace lint tool: detects stale/mismatched derived state files.
Run with --check (default), --fix, or --json.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── project root ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# ── phase rules (lazy load) ──────────────────────────────────────────────────
_PHASE_RULES: dict | None = None


def _load_phase_rules() -> dict:
    global _PHASE_RULES
    if _PHASE_RULES is None:
        with open(PROJECT_ROOT / "orchestration" / "phase_rules.json") as f:
            _PHASE_RULES = json.load(f)
    return _PHASE_RULES


# ── Phase computation (mirrors update_project_state.py) ─────────────────────
_PHASE_ORDER = ["P0", "P0.5", "P1", "P1.5", "P2", "P3", "P4", "P5", "P6", "P7"]


def _gate_is_passed(workspace: Path, gate_id: str) -> bool:
    gates_path = workspace / "approval_gates.json"
    if not gates_path.exists():
        return False
    try:
        gates = json.loads(gates_path.read_text()).get("gates", {})
        gate = gates.get(gate_id, {})
        return gate.get("status") == "approved"
    except Exception:
        return False


def _planning_outputs_exist(workspace: Path) -> bool:
    return all(
        (workspace / p).exists()
        for p in [
            "05_planning/writing_blueprint.json",
            "05_planning/structure_index.json",
        ]
    )


def _review_outputs_exist(workspace: Path) -> bool:
    return (workspace / "08_review/internal_review_report.json").exists()


def _all_bucket_files_exist(workspace: Path) -> bool:
    buckets_dir = workspace / "06_buckets"
    if not buckets_dir.is_dir():
        return False
    return any(buckets_dir.glob("SEC-*.json"))


def _all_draft_meta_files_exist(workspace: Path) -> bool:
    drafts_dir = workspace / "07_drafts"
    if not drafts_dir.is_dir():
        return False
    return any(drafts_dir.glob("SEC-*_meta.json"))


def compute_current_phase(workspace: Path) -> str:
    """Replicate the determine_phase logic from update_project_state.py."""
    p0_done = (workspace / "00_definition/project_charter.json").exists() and (
        workspace / "00_definition/stakeholder_matrix.json"
    ).exists()
    if not p0_done and (workspace / "02_file_registry/file_registry.json").exists():
        p0_done = True

    p1_done = (workspace / "02_file_registry/file_registry.json").exists() and (
        workspace / "04_segments/segment_manifest.json"
    ).exists()

    p05_done = (workspace / "00_definition/intake_manifest.json").exists()
    if not p05_done and p1_done:
        p05_done = True

    toc_draft_path = workspace / "05_planning/toc_draft.json"
    p15_toc_exists = toc_draft_path.exists()
    p15_gate_passed = _gate_is_passed(workspace, "P1.5_to_P2")
    p15_done = p15_toc_exists and p15_gate_passed
    if not p15_done and _planning_outputs_exist(workspace):
        p15_done = True

    p2_done = _planning_outputs_exist(workspace) and _gate_is_passed(workspace, "P2_to_P3")
    p3_done = _all_bucket_files_exist(workspace)
    p4_done = _all_draft_meta_files_exist(workspace)
    p5_done = _review_outputs_exist(workspace) and _gate_is_passed(workspace, "P5_to_P6")
    p6_done = (workspace / "09_handoff/draft_package.json").exists()
    p7_done = (workspace / "10_evidence_pack/evidence_chain.json").exists()

    completed = {
        "P0": p0_done,
        "P0.5": p05_done,
        "P1": p1_done,
        "P1.5": p15_done,
        "P2": p2_done,
        "P3": p3_done,
        "P4": p4_done,
        "P5": p5_done,
        "P6": p6_done,
        "P7": p7_done,
    }

    for i, phase in enumerate(_PHASE_ORDER):
        if not completed[phase]:
            return phase if i > 0 else _PHASE_ORDER[0]
    return "P7"


# ── Gate prerequisite map ────────────────────────────────────────────────────
_GATE_PREREQUISITES: dict[str, list[str]] = {
    "GATE-P05-TO-P1": ["00_definition/intake_manifest.json"],
    "GATE-P15-TO-P2": ["05_planning/toc_draft.json"],
    "P2_to_P3": ["05_planning/writing_blueprint.json", "05_planning/structure_index.json"],
    "P5_to_P6": ["08_review/internal_review_report.json"],
}


# ── Normalized meta fields (PKT-B002) ────────────────────────────────────────
_NORMALIZED_META_FIELDS = frozenset(
    [
        "heading_ko",
        "draft_confidence",
        "evidence_segments",
        "placeholders",
        "missing_evidence",
    ]
)

_LEGACY_FIELD_MAP: dict[str, str] = {
    "heading_text": "heading_ko",
    "confidence": "draft_confidence",
    "evidence_refs": "evidence_segments",
    "placeholder_list": "placeholders",
    "gap_items": "missing_evidence",
}


# ── Check implementations ────────────────────────────────────────────────────
class CheckResult:
    def __init__(self, name: str) -> None:
        self.name = name
        self.status: str = "pass"  # pass | warning | error
        self.details: str = ""


def check_phase_consistency(workspace: Path) -> CheckResult:
    result = CheckResult("PHASE_CONSISTENCY")
    state_path = workspace / "project_state.json"
    if not state_path.exists():
        result.status = "error"
        result.details = "project_state.json not found"
        return result

    try:
        state = json.loads(state_path.read_text())
    except Exception as exc:
        result.status = "error"
        result.details = f"Failed to parse project_state.json: {exc}"
        return result

    stated_phase = state.get("current_phase", "unknown")
    computed_phase = compute_current_phase(workspace)

    if stated_phase != computed_phase:
        result.status = "warning"
        result.details = f"current_phase={stated_phase}, computed={computed_phase}"
    else:
        result.details = f"current_phase={stated_phase}, computed={computed_phase}"

    return result


def check_gate_consistency(workspace: Path) -> CheckResult:
    result = CheckResult("GATE_CONSISTENCY")
    gates_path = workspace / "approval_gates.json"
    if not gates_path.exists():
        result.status = "warning"
        result.details = "approval_gates.json not found"
        return result

    try:
        data = json.loads(gates_path.read_text())
        gates: dict[str, dict] = data.get("gates", {})
    except Exception as exc:
        result.status = "error"
        result.details = f"Failed to parse approval_gates.json: {exc}"
        return result

    warnings: list[str] = []

    for gate_id, prereqs in _GATE_PREREQUISITES.items():
        gate = gates.get(gate_id, {})
        gate_status = gate.get("status", "unknown")
        if gate_status == "approved":
            for prereq in prereqs:
                if not (workspace / prereq).exists():
                    warnings.append(f"{gate_id} approved but {prereq} missing")
        elif gate_status == "waiting":
            # Check if prerequisites exist (guide user)
            if all((workspace / prereq).exists() for prereq in prereqs):
                warnings.append(f"{gate_id} waiting but all prerequisites exist")

    if warnings:
        result.status = "warning"
        result.details = " | ".join(warnings)
    else:
        result.details = "OK"

    return result


def check_next_actions_stale(workspace: Path) -> CheckResult:
    result = CheckResult("NEXT_ACTIONS_STALE")
    na_path = workspace / "next_actions.json"
    if not na_path.exists():
        result.status = "warning"
        result.details = "next_actions.json not found"
        return result

    try:
        na = json.loads(na_path.read_text())
    except Exception as exc:
        result.status = "error"
        result.details = f"Failed to parse next_actions.json: {exc}"
        return result

    updated_at_str = na.get("updated_at") or na.get("last_updated")
    if not updated_at_str:
        result.status = "warning"
        result.details = "No updated_at/last_updated field"
        return result

    try:
        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
    except Exception:
        result.status = "warning"
        result.details = f"Invalid updated_at format: {updated_at_str}"
        return result

    # Find latest mtime among all derived-state and phase-output files
    watch_paths = [
        workspace / "project_state.json",
        workspace / "approval_gates.json",
        workspace / "draft_queries.json",
        workspace / "00_definition",
        workspace / "05_planning",
        workspace / "07_drafts",
    ]

    latest_mtime: datetime | None = None
    for wp in watch_paths:
        if wp.is_file():
            mtime = datetime.fromtimestamp(wp.stat().st_mtime, tz=timezone.utc)
            latest_mtime = mtime if latest_mtime is None else max(latest_mtime, mtime)
        elif wp.is_dir():
            for child in wp.rglob("*"):
                if child.is_file():
                    mtime = datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc)
                    latest_mtime = mtime if latest_mtime is None else max(latest_mtime, mtime)

    if latest_mtime is not None and latest_mtime > updated_at:
        result.status = "warning"
        result.details = (
            f"next_actions.json updated at {updated_at_str}, but artifacts changed at {latest_mtime.isoformat()}"
        )
    else:
        result.details = "OK"

    return result


def check_open_queries(workspace: Path) -> CheckResult:
    result = CheckResult("OPEN_QUERIES")
    dq_path = workspace / "draft_queries.json"
    if not dq_path.exists():
        result.status = "warning"
        result.details = "draft_queries.json not found"
        return result

    try:
        dq = json.loads(dq_path.read_text())
    except Exception as exc:
        result.status = "error"
        result.details = f"Failed to parse draft_queries.json: {exc}"
        return result

    queries = dq.get("queries", [])
    open_queries = [q for q in queries if q.get("status") == "open"]

    if not open_queries:
        result.details = "OK (0 open queries)"
        return result

    # Load section progress from project_state
    state_path = workspace / "project_state.json"
    section_progress: dict[str, dict] = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            section_progress = state.get("section_progress", {})
        except Exception:
            pass

    warnings: list[str] = []
    for q in open_queries:
        qid = q.get("id", "DQ-???")
        section_id = q.get("section_id")
        if section_id and section_id in section_progress:
            sec_status = section_progress[section_id].get("status", "")
            if sec_status in ("approved", "final"):
                warnings.append(f"{qid} open but {section_id} already {sec_status}")

    if warnings:
        result.status = "warning"
        result.details = f"{len(open_queries)} open queries | {'; '.join(warnings[:3])}"
    else:
        result.details = f"{len(open_queries)} open queries (no conflicts detected)"

    return result


def check_meta_field_names(workspace: Path) -> CheckResult:
    result = CheckResult("META_FIELD_CHECK")
    drafts_dir = workspace / "07_drafts"
    if not drafts_dir.is_dir():
        result.status = "warning"
        result.details = "07_drafts/ directory not found"
        return result

    meta_files = sorted(drafts_dir.glob("SEC-*_meta.json"))
    if not meta_files:
        result.details = "OK (no draft meta files)"
        return result

    legacy_reports: list[str] = []
    for mf in meta_files:
        try:
            meta = json.loads(mf.read_text())
        except Exception as exc:
            legacy_reports.append(f"{mf.name}: parse error {exc}")
            continue

        used_legacy = [(old, _LEGACY_FIELD_MAP[old]) for old in _LEGACY_FIELD_MAP if old in meta]
        if used_legacy:
            legacy_reports.append(
                f"{mf.name} uses legacy field(s): " + ", ".join(f"'{o}' instead of '{n}'" for o, n in used_legacy)
            )

    if legacy_reports:
        result.status = "warning"
        result.details = f"{len(legacy_reports)} file(s) with legacy fields | " + legacy_reports[0]
    else:
        result.details = f"OK ({len(meta_files)} files, all normalized)"

    return result


# ── Fix implementations ──────────────────────────────────────────────────────
def _backup(path: Path) -> None:
    if path.exists():
        bak = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, bak)


def fix_phase_state(workspace: Path) -> str:
    _backup(workspace / "project_state.json")
    # Re-run determine_phase and regenerate project_state
    from scripts.update_project_state import build_project_state_snapshot

    snapshot = build_project_state_snapshot(workspace)
    out_path = workspace / "project_state.json"
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return f"Updated project_state.json (current_phase={snapshot.get('current_phase')})"


def fix_next_actions(workspace: Path) -> str:
    _backup(workspace / "next_actions.json")
    # Regenerate next_actions.json
    from scripts.update_project_state import generate_narrative_status

    state_path = workspace / "project_state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
    else:
        state = {}

    na = generate_narrative_status(state)
    out_path = workspace / "next_actions.json"
    out_path.write_text(json.dumps(na, ensure_ascii=False, indent=2))
    return "Regenerated next_actions.json"


# ── CLI ───────────────────────────────────────────────────────────────────────
def _run_checks(workspace: Path) -> dict[str, CheckResult]:
    return {
        "PHASE_CONSISTENCY": check_phase_consistency(workspace),
        "GATE_CONSISTENCY": check_gate_consistency(workspace),
        "NEXT_ACTIONS_STALE": check_next_actions_stale(workspace),
        "OPEN_QUERIES": check_open_queries(workspace),
        "META_FIELD_CHECK": check_meta_field_names(workspace),
    }


def _format_text(workspace: Path, results: dict[str, CheckResult]) -> str:
    lines = [f"=== Workspace Doctor: {workspace.name} ===\n"]
    passed = warnings = errors = 0

    for name, r in results.items():
        if r.status == "pass":
            icon = "✅"
            passed += 1
        elif r.status == "warning":
            icon = "⚠️ "
            warnings += 1
        else:
            icon = "❌"
            errors += 1

        lines.append(f"{icon} {name}: {r.details}")

    total = passed + warnings + errors
    lines.append(f"\n--- Summary ---")
    lines.append(f"Checks: {total} | Passed: {passed} | Warnings: {warnings} | Errors: {errors}")
    lines.append("\nRun with --fix to auto-repair fixable issues.")
    return "\n".join(lines)


def _format_json(workspace: Path, results: dict[str, CheckResult]) -> str:
    summary = {"total": len(results), "passed": 0, "warnings": 0, "errors": 0}
    checks = []
    for name, r in results.items():
        if r.status == "pass":
            summary["passed"] += 1
        elif r.status == "warning":
            summary["warnings"] += 1
        else:
            summary["errors"] += 1
        checks.append({"name": name, "status": r.status, "details": r.details})

    output = {
        "workspace": workspace.name,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": summary,
    }
    return json.dumps(output, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Workspace Doctor — lint derived state files")
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="Path to project workspace",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check only (default)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Check and auto-repair fixable issues",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args(argv)

    ws = args.workspace.resolve()
    if not ws.is_dir():
        print(f"ERROR: {ws} is not a directory", file=sys.stderr)
        return 2

    results = _run_checks(ws)

    if args.json:
        print(_format_json(ws, results))
    else:
        print(_format_text(ws, results))

    if args.fix:
        print("\n=== Applying fixes ===")
        # Phase state fix
        if results["PHASE_CONSISTENCY"].status != "pass":
            try:
                msg = fix_phase_state(ws)
                print(f"  • {msg}")
            except Exception as exc:
                print(f"  • PHASE_CONSISTENCY fix failed: {exc}", file=sys.stderr)

        # Next-actions stale fix
        if results["NEXT_ACTIONS_STALE"].status != "pass":
            try:
                msg = fix_next_actions(ws)
                print(f"  • {msg}")
            except Exception as exc:
                print(f"  • NEXT_ACTIONS_STALE fix failed: {exc}", file=sys.stderr)

        # Meta field check: report only, no auto-fix (migration script is separate)
        if results["META_FIELD_CHECK"].status != "pass":
            print("  • META_FIELD_CHECK: manual migration required (run migrate_draft_meta.py --apply per file)")

        # Re-run checks after fix
        results = _run_checks(ws)
        if not args.json:
            print("\n=== After fix ===")
            print(_format_text(ws, results))

    # Exit code
    has_errors = any(r.status == "error" for r in results.values())
    has_warnings = any(r.status == "warning" for r in results.values())
    if has_errors:
        return 2
    if has_warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
