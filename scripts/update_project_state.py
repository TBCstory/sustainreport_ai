#!/usr/bin/env python3.13
"""
project_state.json 갱신 스크립트

사용법:
  python scripts/update_project_state.py --workspace /path/to/PRJ-YYYY-CODE-NNN
  python scripts/update_project_state.py --workspace /path/to/PRJ-YYYY-CODE-NNN --force  # 강제 갱신
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

# ---------------------------------------------------------------------------
# Phase determination logic
# ---------------------------------------------------------------------------


def determine_phase(workspace: Path, phase_rules: dict) -> tuple[str, dict[str, str]]:
    """
    Determine the current phase and status for each phase.
    Returns (current_phase, phase_status_dict).
    """
    phase_order = ["P0", "P0.5", "P1", "P1.5", "P2", "P3", "P4", "P5", "P6", "P7"]

    # P0: complete if definition files exist.
    # If P0 files are absent but P1 outputs exist, P0 was implicitly completed
    # (entered via --skip-approval or fresh-lane testing without P0 setup).
    p0_done = (workspace / "00_definition" / "project_charter.json").exists() and (
        workspace / "00_definition" / "stakeholder_matrix.json"
    ).exists()
    if not p0_done and (workspace / "02_file_registry" / "file_registry.json").exists():
        # P1 outputs exist → P0 was implicitly done (skipped)
        p0_done = True
    # P1: complete if file_registry and segment_manifest exist
    p1_done = (workspace / "02_file_registry" / "file_registry.json").exists() and (
        workspace / "04_segments" / "segment_manifest.json"
    ).exists()
    # P0.5: complete if intake_manifest.json exists
    # If intake_manifest is absent but P1 outputs exist, P0.5 was implicitly completed
    p05_done = (workspace / "00_definition" / "intake_manifest.json").exists()
    if not p05_done and p1_done:
        p05_done = True
    # P1.5: complete if toc_draft.json exists AND P1.5_to_P2 gate is passed
    toc_draft_path = workspace / "05_planning" / "toc_draft.json"
    p15_toc_exists = toc_draft_path.exists()
    p15_gate_passed = _gate_is_passed(workspace, "P1.5_to_P2")
    p15_done = p15_toc_exists and p15_gate_passed
    # If toc_draft is absent but P2 planning outputs exist, P1.5 was implicitly completed
    if not p15_done and _planning_outputs_exist(workspace):
        p15_done = True
    # P2/P5 are gated phases, so phase completion must agree with gate evaluation.
    p2_done = _planning_outputs_exist(workspace) and _gate_is_passed(workspace, "P2_to_P3")
    # P3: complete if all bucket files exist
    p3_done = _all_bucket_files_exist(workspace)
    # P4: complete if all draft meta files exist
    p4_done = _all_draft_meta_files_exist(workspace)
    # P5 must agree with the review gate as well.
    p5_done = _review_outputs_exist(workspace) and _gate_is_passed(workspace, "P5_to_P6")
    # P6: complete if handoff package exists
    p6_done = (workspace / "09_handoff" / "draft_package.json").exists()
    # P7: complete if evidence pack exists
    p7_done = (workspace / "10_evidence_pack" / "evidence_chain.json").exists()

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

    phase_status: dict[str, str] = {}
    current_phase = "P0"

    for i, phase in enumerate(phase_order):
        if completed[phase]:
            phase_status[phase] = "complete"
            if i < len(phase_order) - 1:
                current_phase = phase_order[i + 1]
        else:
            if phase == current_phase:
                phase_status[phase] = "in_progress"
            else:
                phase_status[phase] = "pending"
            # All subsequent phases are pending
            for later in phase_order[i + 1 :]:
                phase_status[later] = "pending"
            break
    else:
        # All phases complete
        current_phase = "P7"
        phase_status["P7"] = "complete"

    return current_phase, phase_status


def _planning_outputs_exist(workspace: Path) -> bool:
    """Return True when the core P2 outputs needed for P3 entry all exist."""
    planning_dir = workspace / "05_planning"
    required_files = (
        "writing_blueprint.json",
        "structure_index.json",
        "section_manifest.json",
    )
    return all((planning_dir / name).exists() for name in required_files)


def _review_outputs_exist(workspace: Path) -> bool:
    """Return True when the core P5 review outputs exist."""
    review_dir = workspace / "08_review"
    return (review_dir / "internal_review_report.json").exists() and (review_dir / "fact_check_report.json").exists()


def _gate_is_passed(workspace: Path, gate_name: str) -> bool:
    """Evaluate a human gate using the same logic as check-gate."""
    try:
        from scripts.check_gate import GateEvaluator
    except Exception:
        return False

    orchestration_dir = Path(__file__).parent.parent / "orchestration"
    try:
        evaluator = GateEvaluator(workspace=workspace, orchestration_dir=orchestration_dir)
        return evaluator.evaluate(gate_name).get("result") == "passed"
    except Exception:
        return False


def _get_required_section_ids_from_structure(workspace: Path) -> set[str]:
    """Extract required section IDs from structure_index.json."""
    structure_path = workspace / "05_planning" / "structure_index.json"
    if not structure_path.exists():
        return set()
    try:
        data = json.loads(structure_path.read_text(encoding="utf-8"))
        return {
            entry["section_id"] for entry in data.get("entries", []) if entry.get("section_id", "").startswith("SEC-")
        }
    except (json.JSONDecodeError, OSError, KeyError):
        return set()


def _get_required_section_ids_from_manifest(workspace: Path) -> set[str]:
    """Extract required (non-manual) section IDs from section_manifest.json.

    WP-6: section_manifest.json is the authoritative source for required sections.
    manual sections are excluded from completion calculations.
    """
    manifest_path = workspace / "05_planning" / "section_manifest.json"
    if not manifest_path.exists():
        # Fallback to structure_index.json if manifest doesn't exist
        return _get_required_section_ids_from_structure(workspace)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            entry["section_id"]
            for entry in data.get("sections", [])
            if entry.get("section_id", "").startswith("SEC-") and entry.get("writing_mode", "flex") != "manual"
        }
    except (json.JSONDecodeError, OSError, KeyError):
        return set()


def _all_bucket_files_exist(workspace: Path) -> bool:
    """Check if all required bucket files (SEC-*.json) exist in 06_buckets/.

    Uses section_manifest.json (authoritative) to determine required section_ids.
    manual sections are excluded.
    Falls back to structure_index.json if manifest doesn't exist.
    """
    buckets_dir = workspace / "06_buckets"
    if not buckets_dir.is_dir():
        return False

    # Get required section_ids from section_manifest (excludes manual)
    required_sections = _get_required_section_ids_from_manifest(workspace)
    if not required_sections:
        # Fallback: if no manifest, check if any bucket exists
        return any(buckets_dir.glob("SEC-*.json"))

    # Check all required sections have their bucket files
    return all((buckets_dir / f"{section_id}.json").exists() for section_id in required_sections)


def _all_draft_meta_files_exist(workspace: Path) -> bool:
    """Check if all required draft meta files (SEC-*_meta.json) exist in 07_drafts/.

    Uses section_manifest.json (authoritative) to determine required section_ids.
    manual sections are excluded.
    Falls back to structure_index.json if manifest doesn't exist.
    """
    drafts_dir = workspace / "07_drafts"
    if not drafts_dir.is_dir():
        return False

    # Get required section_ids from section_manifest (excludes manual)
    required_sections = _get_required_section_ids_from_manifest(workspace)
    if not required_sections:
        # Fallback: if no manifest, check if any draft meta exists
        return any(drafts_dir.glob("SEC-*_meta.json"))

    # Check all required sections have their draft meta files
    return all((drafts_dir / f"{section_id}_meta.json").exists() for section_id in required_sections)


# ---------------------------------------------------------------------------
# Section progress
# ---------------------------------------------------------------------------


def gather_section_progress(workspace: Path) -> dict:
    """
    Gather section progress from 06_buckets and 07_drafts.
    Returns a dict mapping section_id -> {status, draft_version, confidence}.
    Skips manual sections defined in section_manifest.json.
    """
    section_progress: dict = {}

    # Get allowed section IDs (non-manual sections from manifest)
    allowed_section_ids = _get_required_section_ids_from_manifest(workspace)

    # Scan buckets to get all section IDs
    buckets_dir = workspace / "06_buckets"
    section_ids: set[str] = set()

    if buckets_dir.is_dir():
        for bucket_file in buckets_dir.glob("SEC-*.json"):
            # Extract section_id from filename like "SEC-3.1.json"
            name = bucket_file.stem  # e.g. "SEC-3.1"
            if not allowed_section_ids or name in allowed_section_ids:
                section_ids.add(name)

    # Also scan drafts for additional section IDs
    drafts_dir = workspace / "07_drafts"
    if drafts_dir.is_dir():
        for draft_file in drafts_dir.glob("SEC-*_meta.json"):
            # Extract section_id from filename like "SEC-3.1_meta.json"
            name = draft_file.stem  # e.g. "SEC-3.1_meta"
            if name.endswith("_meta"):
                section_id = name[:-5]  # Remove "_meta"
            else:
                section_id = name
            if not allowed_section_ids or section_id in allowed_section_ids:
                section_ids.add(section_id)

    for section_id in sorted(section_ids):
        bucket_path = workspace / "06_buckets" / f"{section_id}.json"
        meta_path = workspace / "07_drafts" / f"{section_id}_meta.json"

        status = "pending"
        draft_version: Optional[int] = None
        confidence: Optional[float] = None

        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                confidence = meta.get("draft_confidence")
                draft_version = meta.get("draft_version")

                if confidence is not None and confidence >= 0.8:
                    status = "approved"
                else:
                    status = "drafted"
            except (json.JSONDecodeError, OSError):
                status = "drafted"
        elif bucket_path.exists():
            status = "in_progress"

        entry: dict = {"status": status}
        if draft_version is not None:
            entry["draft_version"] = draft_version
        if confidence is not None:
            entry["confidence"] = round(confidence, 2)

        section_progress[section_id] = entry

    return section_progress


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def compute_statistics(
    workspace: Path,
    section_progress: dict,
    phase_rules: dict,
) -> dict:
    """Compute overall statistics for the project."""
    total_segments = 0
    segments_processed = 0
    total_sections = len(section_progress)
    sections_drafted = sum(1 for s in section_progress.values() if s["status"] in ("drafted", "approved"))
    sections_approved = sum(1 for s in section_progress.values() if s["status"] == "approved")

    # Load segment manifest if available
    seg_manifest_path = workspace / "04_segments" / "segment_manifest.json"
    if seg_manifest_path.exists():
        try:
            seg_manifest = json.loads(seg_manifest_path.read_text(encoding="utf-8"))
            total_segments = seg_manifest.get("total_segments", 0)
            segments_processed = seg_manifest.get("segments_processed", total_segments)
        except (json.JSONDecodeError, OSError):
            pass

    # Compute average draft confidence
    confidences = [
        s["confidence"] for s in section_progress.values() if "confidence" in s and s["confidence"] is not None
    ]
    draft_confidence_avg = round(sum(confidences) / len(confidences), 2) if confidences else 0.0

    return {
        "total_segments": total_segments,
        "segments_processed": segments_processed,
        "total_sections": total_sections,
        "sections_drafted": sections_drafted,
        "sections_approved": sections_approved,
        "draft_confidence_avg": draft_confidence_avg,
    }


# ---------------------------------------------------------------------------
# Project ID extraction
# ---------------------------------------------------------------------------


def extract_project_id(workspace: Path) -> str:
    """Extract project_id from project_charter.json or infer from path."""
    charter_path = workspace / "00_definition" / "project_charter.json"
    if charter_path.exists():
        try:
            charter = json.loads(charter_path.read_text(encoding="utf-8"))
            if "project_id" in charter:
                return charter["project_id"]
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: infer from workspace path
    # e.g. /path/to/workspaces/PRJ-2026-0402-ESG001 -> PRJ-2026-0402-ESG001
    for parent in workspace.parents:
        if parent.name == "workspaces":
            return workspace.name
    return workspace.name


# ---------------------------------------------------------------------------
# Main update logic
# ---------------------------------------------------------------------------


def build_project_state_snapshot(workspace: Path) -> dict:
    """Build a live project state snapshot without writing it to disk."""
    # Load phase rules
    phase_rules_path = Path(__file__).parent.parent / "orchestration" / "phase_rules.json"
    if not phase_rules_path.exists():
        raise FileNotFoundError(f"phase_rules.json not found: {phase_rules_path}")

    phase_rules = json.loads(phase_rules_path.read_text(encoding="utf-8"))

    # Determine project_id
    project_id = extract_project_id(workspace)

    # Determine current phase and phase statuses
    current_phase, phase_status = determine_phase(workspace, phase_rules)

    # Gather section progress
    section_progress = gather_section_progress(workspace)

    # Compute statistics
    statistics = compute_statistics(workspace, section_progress, phase_rules)

    # Build new state
    new_state: dict = {
        "project_id": project_id,
        "current_phase": current_phase,
        "phase_status": phase_status,
        "section_progress": section_progress,
        "statistics": statistics,
        "last_updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "updated_by": "update_project_state.py",
    }

    return new_state


def update_project_state(workspace: Path, force: bool = False) -> dict:
    """
    Build or update project_state.json for the given workspace.
    Returns the new state dict.
    """
    new_state = build_project_state_snapshot(workspace)

    state_path = workspace / "project_state.json"

    # Write to file
    state_path.write_text(
        json.dumps(new_state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return new_state


# ---------------------------------------------------------------------------
# Narrative helper — Natural Language Orchestrator UX Surface (OD-7)
# ---------------------------------------------------------------------------


def _load_json_capture(path: Path) -> dict | None:
    """Load JSON file, returning None on failure."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def generate_narrative_status(workspace: Path) -> str:
    """
    Generate a natural-language status summary suitable for AI session consumption.

    Returns a narrative block containing:
    - Current phase with completion status
    - Top blockers (up to 3)
    - Open draft queries (up to 3)
    - Next actions (up to 3)
    - Blueprint approval status (if P2)

    This is the canonical "narrative helper" for OD-7.
    """
    project_id = workspace.name
    lines: list[str] = []

    # --- Phase and state ---
    try:
        state = build_project_state_snapshot(workspace)
    except Exception:
        state = _load_json_capture(workspace / "project_state.json") or {}

    current_phase = state.get("current_phase", "P0")
    phase_status = state.get("phase_status", {})
    statistics = state.get("statistics", {})
    section_progress = state.get("section_progress", {})

    phase_names = {
        "P0": "프로젝트 정의",
        "P1": "자료 투입",
        "P2": "기획 (Blueprint)",
        "P3": "버킷 구축",
        "P4": "초안 작성",
        "P5": "검수",
        "P6": "핸드오프",
        "P7": "증거 패키지",
    }
    phase_name = phase_names.get(current_phase, current_phase)
    current_status = phase_status.get(current_phase, "unknown")

    # --- Blueprint approval status (only relevant in P2) ---
    bp_approved = None
    bp_path = workspace / "05_planning" / "writing_blueprint.json"
    if bp_path.exists():
        bp = _load_json_capture(bp_path)
        if bp:
            bp_approved = bp.get("approved", False)

    approval_gates_path = workspace / "approval_gates.json"
    approval_data = _load_json_capture(approval_gates_path) or {}
    gates: dict = approval_data.get("gates", {})

    pending_gates = [g for g, info in gates.items() if info.get("status") in ("waiting", "pending")]

    # --- Blocking issues ---
    bi_path = workspace / "blocking_issues.json"
    blocking_issues = []
    if bi_path.exists():
        bi = _load_json_capture(bi_path)
        if bi:
            issues = bi.get("issues", [])
            open_issues = [i for i in issues if i.get("status") != "resolved"]
            blocking_issues = sorted(
                open_issues,
                key=lambda x: (0 if x.get("severity") == "blocker" else 1, x.get("issue_id", "")),
            )[:3]

    # --- Draft queries ---
    dq_path = workspace / "draft_queries.json"
    open_queries = []
    if dq_path.exists():
        dq = _load_json_capture(dq_path)
        if dq:
            queries = dq.get("queries", []) if isinstance(dq, dict) else dq
            open_queries = [q for q in queries if q.get("status") == "open"][:3]

    # --- Next actions ---
    na_path = workspace / "next_actions.json"
    next_actions = []
    if na_path.exists():
        na = _load_json_capture(na_path)
        if na:
            pending = [a for a in na.get("actions", []) if a.get("status") != "completed"]
            next_actions = sorted(pending, key=lambda a: a.get("priority", 99))[:3]

    # --- Build narrative ---
    lines.append(f"프로젝트 '{project_id}' 현황:")
    lines.append("")

    # Phase line
    status_icon = "✓" if current_status == "complete" else "→" if current_status == "in_progress" else "○"
    lines.append(f"  {status_icon} Phase {current_phase} ({phase_name}): {current_status}")

    # Statistics
    if statistics:
        segs = statistics.get("segments_processed", 0)
        total_segs = statistics.get("total_segments", 0)
        sections_drafted = statistics.get("sections_drafted", 0)
        total_sections = statistics.get("total_sections", 0)
        if total_segs > 0:
            lines.append(f"    - 세그먼트: {segs}/{total_segs} 처리됨")
        if total_sections > 0:
            lines.append(f"    - 섹션: {sections_drafted}/{total_sections} 초안 작성됨")

    # Blueprint approval
    if current_phase == "P2":
        if bp_approved is True:
            lines.append("  ✓ writing_blueprint: 승인 완료")
        elif bp_approved is False:
            lines.append("  ○ writing_blueprint: 검토 대기 중")
        else:
            lines.append("  ○ writing_blueprint: 승인 상태 불확실")

    # Pending gates
    if pending_gates:
        lines.append(f"  ○ 대기 중인 승인 게이트: {', '.join(pending_gates)}")

    # Blocking issues
    if blocking_issues:
        lines.append("")
        lines.append("  차단 요인 (Blockers):")
        for i, issue in enumerate(blocking_issues, 1):
            severity = issue.get("severity", "?")
            issue_id = issue.get("issue_id", "?")
            desc = issue.get("description", "")[:60]
            section = issue.get("section_id", "")
            sec_part = f" [{section}]" if section else ""
            lines.append(f"    {i}. [{severity}] {issue_id}{sec_part} — {desc}")
    else:
        lines.append("")
        lines.append("  차단 요인: 없음")

    # Open queries
    if open_queries:
        lines.append("")
        lines.append("  미해결 질의 (Open Queries):")
        for i, q in enumerate(open_queries, 1):
            qid = q.get("query_id", "?")
            section = q.get("section_id", "")
            question = q.get("question", q.get("description", ""))[:50]
            sec_part = f" [{section}]" if section else ""
            lines.append(f"    {i}. {qid}{sec_part} — {question}")
    else:
        lines.append("")
        lines.append("  미해결 질의: 없음")

    # Next actions
    if next_actions:
        lines.append("")
        lines.append(f"  다음 행동 (Top {len(next_actions)}):")
        for i, act in enumerate(next_actions, 1):
            act_id = act.get("action_id", "?")
            act_type = act.get("type", "?")
            desc = act.get("description", "")[:55]
            section = act.get("section_id", "")
            sec_part = f" [{section}]" if section else ""
            lines.append(f"    {i}. [{act_type}]{sec_part} {act_id} — {desc}")
    else:
        lines.append("")
        lines.append("  다음 행동: 없음 (모든 작업 완료)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--workspace",
    "-w",
    "workspace",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="경로: /path/to/PRJ-YYYY-CODE-NNN",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="기존 project_state.json 무시하고 처음부터 생성",
)
def main(workspace: Path, force: bool) -> int:
    """project_state.json 갱신 스크립트"""
    try:
        state = update_project_state(workspace, force=force)
        click.echo(f"project_state.json updated: {workspace / 'project_state.json'}")
        click.echo(f"  project_id:   {state['project_id']}")
        click.echo(f"  current_phase: {state['current_phase']}")
        click.echo(f"  phase_status: {state['phase_status']}")
        click.echo(f"  statistics:   {state['statistics']}")
        return 0
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        return 1
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
