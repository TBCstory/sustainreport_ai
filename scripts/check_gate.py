#!/usr/bin/env python3.13
"""
게이트 판정 스크립트 — 페이즈 전환 가능 여부 결정

Usage:
  python scripts/check_gate.py --gate P2_to_P3 --workspace /path/to/PRJ-YYYY-CODE-NNN
  python scripts/check_gate.py --gate auto --from-phase P3 --to-phase P4 --workspace /path/to/PRJ-YYYY-CODE-NNN

반환값:
  0 = 게이트 통과
  1 = 게이트 차단 (blocking conditions 존재)
  2 = 사람 승인 필요
  3 = 자동 통과
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import click

from scripts.state_manager import normalize_approval_gates_data

# Constants for exit codes
EXIT_PASSED = 0
EXIT_BLOCKED = 1
EXIT_HUMAN_APPROVAL = 2
EXIT_AUTO_PASSED = 3

# Phase ordering — mirrors run_pipeline.py
NEXT_PHASE = {
    "P0": "P0.5",
    "P0.5": "P1",
    "P1": "P1.5",
    "P1.5": "P2",
    "P2": "P3",
    "P3": "P4",
    "P4": "P5",
    "P5": "P6",
    "P6": "P7",
    "P7": None,
}


def verify_structure_stability(workspace: Path) -> dict[str, Any]:
    """
    Verify that section_id, heading_anchor, and toc_path are stable
    between structure_index and writing_blueprint.

    Returns a dict with:
      - stable: bool — True if all section IDs match and anchors/toc_paths are consistent
      - section_ids_match: bool
      - anchor_conflicts: list of sections with conflicting anchors
      - toc_path_conflicts: list of sections with conflicting toc_paths
      - errors: list of error messages
    """
    import copy

    structure_path = workspace / "05_planning" / "structure_index.json"
    blueprint_path = workspace / "05_planning" / "writing_blueprint.json"

    errors: list[str] = []
    anchor_conflicts: list[str] = []
    toc_path_conflicts: list[str] = []

    if not structure_path.exists():
        errors.append(f"structure_index.json not found at {structure_path}")
        return {
            "stable": False,
            "section_ids_match": False,
            "anchor_conflicts": [],
            "toc_path_conflicts": [],
            "errors": errors,
        }

    if not blueprint_path.exists():
        errors.append(f"writing_blueprint.json not found at {blueprint_path}")
        return {
            "stable": False,
            "section_ids_match": False,
            "anchor_conflicts": [],
            "toc_path_conflicts": [],
            "errors": errors,
        }

    structure_data = json.loads(structure_path.read_text(encoding="utf-8"))
    blueprint_data = json.loads(blueprint_path.read_text(encoding="utf-8"))

    # Build lookup maps from structure_index
    structure_entries = {e["section_id"]: e for e in structure_data.get("entries", [])}

    # Build lookup from writing_blueprint sections
    blueprint_sections = {s["section_id"]: s for s in blueprint_data.get("sections", [])}

    # Check 1: section_id sets must match
    structure_ids = set(structure_entries.keys())
    blueprint_ids = set(blueprint_sections.keys())

    if structure_ids != blueprint_ids:
        missing_in_blueprint = structure_ids - blueprint_ids
        missing_in_structure = blueprint_ids - structure_ids
        if missing_in_blueprint:
            errors.append(f"section_ids in structure_index but not in blueprint: {sorted(missing_in_blueprint)}")
        if missing_in_structure:
            errors.append(f"section_ids in blueprint but not in structure_index: {sorted(missing_in_structure)}")
        section_ids_match = False
    else:
        section_ids_match = True

    # Check 2: heading_anchor consistency (if section has depth_level >= 2)
    for section_id, struct_entry in structure_entries.items():
        if section_id not in blueprint_sections:
            continue
        bp_section = blueprint_sections[section_id]
        # heading_anchor lives in structure_index only; blueprint inherits it
        # We just verify it exists and is well-formed (lowercase, alphanumeric, hyphens)
        anchor = struct_entry.get("heading_anchor", "")
        if anchor:
            import re

            if not re.match(r"^[a-z0-9][a-z0-9-]*$", anchor):
                anchor_conflicts.append(
                    f"{section_id}: invalid anchor '{anchor}' (expected lowercase alphanumeric with hyphens)"
                )
        else:
            anchor_conflicts.append(f"{section_id}: missing heading_anchor")

    # Check 3: toc_path consistency (must be non-empty array for depth_level >= 2)
    for section_id, struct_entry in structure_entries.items():
        if section_id not in blueprint_sections:
            continue
        toc_path = struct_entry.get("toc_path", [])
        if not isinstance(toc_path, list) or len(toc_path) == 0:
            toc_path_conflicts.append(f"{section_id}: toc_path is empty or not an array")

    stable = section_ids_match and len(anchor_conflicts) == 0 and len(toc_path_conflicts) == 0 and len(errors) == 0

    return {
        "stable": stable,
        "section_ids_match": section_ids_match,
        "anchor_conflicts": anchor_conflicts,
        "toc_path_conflicts": toc_path_conflicts,
        "errors": errors,
    }


class GateEvaluator:
    """Evaluates gate conditions for phase transitions."""

    def __init__(self, workspace: Path, orchestration_dir: Path) -> None:
        self.workspace = workspace
        self.orchestration_dir = orchestration_dir
        self.phase_rules = self._load_json(orchestration_dir / "phase_rules.json")
        self.gate_rules = self._load_json(orchestration_dir / "gate_rules.json")
        self.blocking_issues = self._load_blocking_issues()

    def _load_json(self, path: Path) -> dict[str, Any]:
        """Load JSON file."""
        if not path.exists():
            return {}
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _load_blocking_issues(self) -> dict[str, Any]:
        """Load blocking issues file."""
        path = self.workspace / "blocking_issues.json"
        if not path.exists():
            return {"issues": []}
        return self._load_json(path)

    def _get_phase_config(self, phase: str) -> dict[str, Any]:
        """Get phase configuration from phase_rules."""
        return self.phase_rules.get("phases", {}).get(phase, {})

    def _get_gate_config(self, gate_name: str) -> dict[str, Any]:
        """Get gate configuration from gate_rules."""
        return self.gate_rules.get("gates", {}).get(gate_name, {})

    def _load_approval_gates(self) -> dict[str, Any]:
        """Load approval gates file."""
        path = self.workspace / "approval_gates.json"
        if not path.exists():
            return normalize_approval_gates_data({}, project_id=self.workspace.name)
        return normalize_approval_gates_data(self._load_json(path), project_id=self.workspace.name)

    def _check_gate_approved(self, gate_name: str) -> bool:
        """Check if a gate has been approved in approval_gates.json.

        approval_gates.json은 canonical shape로 정규화한 뒤 판정한다.
        """
        approval_data = self._load_approval_gates()
        gate_approval = approval_data.get("gates", {}).get(gate_name, {})
        return gate_approval.get("status") == "approved"

    def _check_file_exists(self, file_path: str) -> bool:
        """Check if a file or directory exists."""
        file_path = file_path.lstrip("/")
        path = self.workspace / file_path
        if "*" in file_path:
            parent = path.parent
            pattern = path.name
            if not parent.exists():
                return False
            return any(parent.glob(pattern))
        return path.exists()

    def _check_file_approved(self, file_path: str) -> bool:
        """Check if a file exists and has approved: true field."""
        path = self.workspace / file_path
        if not path.exists():
            return False
        try:
            data = self._load_json(path)
            return data.get("approved", False) is True
        except (json.JSONDecodeError, OSError):
            return False

    def _check_blueprint_approved(self) -> bool:
        """Check if writing_blueprint is approved."""
        path = self.workspace / "05_planning" / "writing_blueprint.json"
        if not path.exists():
            return False
        data = self._load_json(path)
        return data.get("approved", False) is True

    def _check_review_score(self, threshold: float) -> bool:
        """Check if review score is above threshold."""
        path = self.workspace / "08_review" / "internal_review_report.json"
        if not path.exists():
            return False
        data = self._load_json(path)
        score = data.get("overall_confidence") or 0.0
        return score >= threshold

    def _check_no_blocking_issues(self) -> bool:
        """Check if there are no unresolved blocking issues.

        Handles two canonical shapes:
        - BLK- style: {"status": "resolved"}
        - BK- style:  {"resolved": True}
        """
        issues = self.blocking_issues.get("issues", [])
        if not issues:
            return True

        def _is_unresolved(issue: dict[str, Any]) -> bool:
            if issue.get("status") == "resolved":
                return False
            if issue.get("resolved") is True:
                return False
            return True

        return not any(_is_unresolved(issue) for issue in issues)

    def _check_required_outputs(self, phase: str) -> bool:
        """Check if all required outputs for a phase exist."""
        phase_config = self._get_phase_config(phase)
        required_outputs = phase_config.get("required_outputs", [])

        if not required_outputs:
            return True

        for output in required_outputs:
            file_path = output.get("file", "")
            if not self._check_file_exists(file_path):
                return False
        return True

    def _check_exit_conditions(self, phase: str) -> tuple[bool, list[str]]:
        """Check phase exit conditions. Returns (all_passed, failed_conditions)."""
        phase_config = self._get_phase_config(phase)
        exit_conditions = phase_config.get("exit_conditions", [])

        if not exit_conditions:
            return True, []

        failed: list[str] = []
        for cond in exit_conditions:
            cond_type = cond.get("type", "file_exists")
            path = cond.get("path", cond.get("file", ""))

            if "{workspace}" in path:
                path = path.replace("{workspace}", "").lstrip("/")

            if cond_type == "file_approved":
                if not self._check_file_approved(path):
                    failed.append(f"file_not_approved:{path}")
            elif cond_type == "file_exists":
                if not self._check_file_exists(path):
                    failed.append(f"file_missing:{path}")
            elif cond_type == "phase_complete":
                ref_phase = cond.get("phase", "")
                ref_config = self._get_phase_config(ref_phase)
                ref_outputs = ref_config.get("required_outputs", [])
                if ref_outputs:
                    if not self._check_required_outputs(ref_phase):
                        failed.append(f"phase_incomplete:{ref_phase}")
            elif cond_type == "minimum_segments":
                threshold = cond.get("count", 0)
                seg_path = self.workspace / "04_segments" / "segment_manifest.json"
                if not seg_path.exists():
                    failed.append(f"segments_below_minimum:{threshold}")
                else:
                    data = self._load_json(seg_path)
                    count = data.get("total_segments", 0)
                    if count < threshold:
                        failed.append(f"segments_below_minimum:{threshold}")
            elif cond_type == "review_complete":
                # Check if internal review report exists and review is complete
                review_path = self.workspace / "08_review" / "internal_review_report.json"
                if not review_path.exists():
                    failed.append("review_not_complete:internal_review_report_missing")
                else:
                    data = self._load_json(review_path)
                    if data.get("review_phase") != "P5":
                        failed.append("review_not_complete:wrong_phase")
            elif cond_type == "handoff_package_complete":
                # Check if handoff package exists
                handoff_path = self.workspace / "09_handoff" / "draft_package.json"
                if not handoff_path.exists():
                    failed.append("handoff_package_incomplete:draft_package_missing")
            elif cond_type == "evidence_pack_complete":
                # Check if evidence pack exists
                evidence_path = self.workspace / "10_evidence_pack" / "evidence_chain.json"
                if not evidence_path.exists():
                    failed.append("evidence_pack_incomplete:evidence_chain_missing")
            elif cond_type == "all_sections_drafted":
                # Check if all required sections have draft meta files
                # Load section_manifest to get required section count
                manifest_path = self.workspace / "05_planning" / "section_manifest.json"
                if not manifest_path.exists():
                    failed.append("drafts_incomplete:section_manifest_missing")
                else:
                    manifest_data = self._load_json(manifest_path)
                    sections = manifest_data.get("sections", [])
                    # Count non-manual sections (rigid + flex need drafts)
                    required_sections = [s for s in sections if s.get("writing_mode") != "manual"]
                    required_count = len(required_sections)

                    draft_dir = self.workspace / "07_drafts"
                    if not draft_dir.exists():
                        failed.append("drafts_incomplete:drafts_directory_missing")
                    else:
                        draft_files = list(draft_dir.glob("SEC-*_meta.json"))
                        draft_count = len(draft_files)
                        if draft_count < required_count:
                            failed.append(f"drafts_incomplete:expected_{required_count}_got_{draft_count}")
            elif path and not self._check_file_exists(path):
                failed.append(f"condition_failed:{cond_type}:{path}")

        return len(failed) == 0, failed

    def _check_entry_conditions(self, phase: str) -> tuple[bool, list[str]]:
        """
        Check phase entry conditions. Returns (all_passed, failed_conditions).
        Failed conditions are also registered to blocking_issues.json.
        """
        phase_config = self._get_phase_config(phase)
        entry_conditions = phase_config.get("entry_conditions", [])

        if not entry_conditions:
            return True, []

        failed: list[str] = []
        for cond in entry_conditions:
            cond_type = cond.get("type", "")
            path = cond.get("path", cond.get("file", ""))

            if "{workspace}" in path:
                path = path.replace("{workspace}", "").lstrip("/")

            if cond_type == "phase_complete":
                ref_phase = cond.get("phase", "")
                ref_config = self._get_phase_config(ref_phase)
                ref_outputs = ref_config.get("required_outputs", [])
                if ref_outputs:
                    if not self._check_required_outputs(ref_phase):
                        failed.append(f"entry_phase_incomplete:{ref_phase}")
            elif cond_type == "minimum_segments":
                threshold = cond.get("count", 0)
                seg_path = self.workspace / "04_segments" / "segment_manifest.json"
                if not seg_path.exists():
                    failed.append(f"entry_segments_below_minimum:{threshold}")
                else:
                    data = self._load_json(seg_path)
                    count = data.get("total_segments", 0)
                    if count < threshold:
                        failed.append(f"entry_segments_below_minimum:{threshold}")
            elif cond_type == "file_exists":
                if not self._check_file_exists(path):
                    failed.append(f"entry_file_missing:{path}")
            elif cond_type == "phase_approved":
                ref_phase = cond.get("phase", "")
                gate_name = f"{ref_phase}_to_{NEXT_PHASE.get(ref_phase, ref_phase + '_next')}"
                if not self._check_gate_approved(gate_name):
                    failed.append(f"entry_gate_not_approved:{gate_name}")

        return len(failed) == 0, failed

    def _register_blocking_issues(self, phase: str, failed_conditions: list[str]) -> None:
        """Register failed entry conditions to blocking_issues.json."""
        issues_path = self.workspace / "blocking_issues.json"
        try:
            if issues_path.exists():
                issues_data = self._load_json(issues_path)
            else:
                issues_data = {"issues": []}
        except (json.JSONDecodeError, OSError):
            issues_data = {"issues": []}

        existing_descriptions = {issue.get("description", "") for issue in issues_data.get("issues", [])}
        new_issues = []
        for cond in failed_conditions:
            description = f"[{phase} entry] {cond}"
            if description not in existing_descriptions:
                new_issues.append(
                    {
                        "issue_id": f"OVR-{len(issues_data['issues']) + len(new_issues) + 1:03d}",
                        "severity": "high",
                        "category": "entry_condition",
                        "section_id": "",
                        "description": description,
                        "status": "open",
                        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
                )

        if new_issues:
            issues_data.setdefault("issues", []).extend(new_issues)
            with open(issues_path, "w", encoding="utf-8") as f:
                json.dump(issues_data, f, ensure_ascii=False, indent=2)

    def _check_critical_fact_errors(self) -> bool:
        """Check for critical fact errors in review."""
        path = self.workspace / "08_review" / "fact_check_report.json"
        if not path.exists():
            return False
        data = self._load_json(path)
        errors = data.get("errors", [])
        return not any(err.get("severity") == "critical" for err in errors)

    def _check_unresolved_conflicts(self) -> bool:
        """Check for unresolved source conflicts."""
        path = self.workspace / "08_review" / "internal_review_report.json"
        if not path.exists():
            return False
        data = self._load_json(path)
        conflicts = data.get("source_conflicts", [])
        return not any(not c.get("resolved", True) for c in conflicts)

    def evaluate_p2_to_p3(self) -> dict[str, Any]:
        """Evaluate P2→P3 Blueprint approval gate."""
        gate_config = self._get_gate_config("P2_to_P3")
        blocking_conditions: list[str] = []

        if not self._check_blueprint_approved():
            blocking_conditions.append("blueprint_not_approved")

        if not self._check_file_exists("05_planning/structure_index.json"):
            blocking_conditions.append("structure_index_missing")

        if blocking_conditions:
            result = "blocked"
            message = "Blueprint 승인 불가. project_manager, consultant_lead 승인 요청."
        elif self._check_gate_approved("P2_to_P3"):
            result = "passed"
            message = "P2→P3 게이트 통과. Blueprint 승인 완료."
        else:
            result = "needs_human_approval"
            message = "Blueprint 생성 완료. project_manager, consultant_lead 승인 대기 중."

        return {
            "gate": "P2_to_P3",
            "result": result,
            "blocking_conditions": blocking_conditions,
            "auto_conditions_met": True,
            "can_override": gate_config.get("can_override", False),
            "message": message,
            "required_approvers": gate_config.get("required_approvers", []),
        }

    def evaluate_p5_to_p6(self) -> dict[str, Any]:
        """Evaluate P5→P6 Review approval gate."""
        gate_config = self._get_gate_config("P5_to_P6")
        blocking_conditions: list[str] = []
        auto_conditions: list[str] = []

        if self._check_review_score(0.8):
            auto_conditions.append("review_score_above")
        else:
            blocking_conditions.append("review_score_below_threshold")

        if self._check_no_blocking_issues():
            auto_conditions.append("no_blocking_issues_remaining")

        if not self._check_critical_fact_errors():
            blocking_conditions.append("critical_fact_errors")

        if not self._check_unresolved_conflicts():
            blocking_conditions.append("unresolved_conflicts")

        # Check if gate is approved in approval_gates.json
        gate_approved = self._check_gate_approved("P5_to_P6")

        if blocking_conditions:
            if gate_approved:
                result = "passed"
                message = "P5→P6 게이트 통과 (override 승인 완료)."
            else:
                result = "blocked"
                message = "검수 차단 조건 존재. 확인 필요."
        elif self._check_gate_approved("P5_to_P6"):
            result = "passed"
            message = "P5→P6 게이트 통과. 검수 승인 완료."
        else:
            result = "needs_human_approval"
            message = "검수 완료. fact_checker, internal_reviewer 승인 요청."

        return {
            "gate": "P5_to_P6",
            "result": result,
            "blocking_conditions": blocking_conditions,
            "auto_conditions_met": len(auto_conditions) == 2,
            "can_override": gate_config.get("can_override", False),
            "message": message,
            "required_approvers": gate_config.get("required_approvers", []),
            "auto_conditions_satisfied": auto_conditions,
        }

    def evaluate_auto_gate(self, from_phase: str, to_phase: str) -> dict[str, Any]:
        """Evaluate auto gate for other phase transitions.

        Note: Entry conditions for to_phase are NOT checked here because:
        1. This gate is evaluated AFTER from_phase execution completes
        2. Entry conditions (e.g., P0 completion before P1) are checked
           by the phase runner itself before returning success
        3. Checking entry conditions here caused side effects (writing to
           blocking_issues.json) during dry-run gate evaluations
        """
        gate_config = self._get_gate_config("auto_gate")
        blocking_conditions: list[str] = []
        auto_conditions_met = True

        # Check required outputs for source phase
        if not self._check_required_outputs(from_phase):
            blocking_conditions.append("required_outputs_missing")
            auto_conditions_met = False

        # Check exit conditions for source phase
        exit_ok, exit_failed = self._check_exit_conditions(from_phase)
        if not exit_ok:
            for f in exit_failed:
                blocking_conditions.append(f"exit_condition_failed:{f}")
            auto_conditions_met = False

        # Check blocking issues
        if not self._check_no_blocking_issues():
            blocking_conditions.append("blocking_issues_remaining")
            auto_conditions_met = False

        if blocking_conditions:
            result = "blocked"
            message = f"{from_phase}→{to_phase} 게이트 차단. 필수 산출물 미완료 또는 차단 이슈 존재."
            exit_code = EXIT_BLOCKED
        else:
            result = "passed"
            message = f"{from_phase}→{to_phase} 자동 통과."
            exit_code = EXIT_AUTO_PASSED

        return {
            "gate": f"{from_phase}_to_{to_phase}",
            "result": result,
            "blocking_conditions": blocking_conditions,
            "auto_conditions_met": auto_conditions_met,
            "can_override": gate_config.get("can_override", False),
            "message": message,
            "exit_code": exit_code,
        }

    def evaluate_p05_to_p1(self) -> dict[str, Any]:
        """P0.5 → P1 자동 게이트: intake_manifest.json 존재 확인."""
        intake_path = self.workspace / "00_definition" / "intake_manifest.json"
        if not intake_path.exists():
            return {
                "gate": "P0.5_to_P1",
                "result": "blocked",
                "blocking_conditions": ["intake_manifest_missing"],
                "auto_conditions_met": False,
                "can_override": True,
                "message": "P0.5→P1 차단: intake_manifest.json 없음. 인테이크 인터뷰를 완료하거나 intake_manifest.json을 수동 생성하세요.",
                "exit_code": EXIT_BLOCKED,
            }
        return {
            "gate": "P0.5_to_P1",
            "result": "passed",
            "blocking_conditions": [],
            "auto_conditions_met": True,
            "can_override": False,
            "message": "P0.5→P1 자동 통과: intake_manifest.json 확인됨.",
            "exit_code": EXIT_AUTO_PASSED,
        }

    def evaluate_p15_to_p2(self) -> dict[str, Any]:
        """P1.5 → P2 사람 승인 게이트: toc_draft.json 존재 + 게이트 승인 확인."""
        toc_draft_path = self.workspace / "05_planning" / "toc_draft.json"
        blocking_conditions = []
        if not toc_draft_path.exists():
            blocking_conditions.append("toc_draft_missing")
        gate_passed = self._check_gate_approved("P1.5_to_P2")
        if not gate_passed:
            blocking_conditions.append("p15_to_p2_not_approved")
        if blocking_conditions:
            return {
                "gate": "P1.5_to_P2",
                "result": "needs_human_approval",
                "blocking_conditions": blocking_conditions,
                "auto_conditions_met": False,
                "can_override": False,
                "message": "P1.5→P2 사람 승인 필요: toc_draft.json 검토 후 'sustainreport approve P1.5_to_P2 --workspace ...' 실행 필요.",
                "exit_code": EXIT_HUMAN_APPROVAL,
            }
        return {
            "gate": "P1.5_to_P2",
            "result": "passed",
            "blocking_conditions": [],
            "auto_conditions_met": True,
            "can_override": False,
            "message": "P1.5→P2 통과: toc_draft 승인됨.",
            "exit_code": EXIT_PASSED,
        }

    def evaluate(
        self, gate_name: str, from_phase: Optional[str] = None, to_phase: Optional[str] = None
    ) -> dict[str, Any]:
        """Evaluate a gate by name."""
        if gate_name == "P2_to_P3":
            return self.evaluate_p2_to_p3()
        elif gate_name == "P5_to_P6":
            return self.evaluate_p5_to_p6()
        elif gate_name in ("P0.5_to_P1", "GATE-P05-TO-P1"):
            return self.evaluate_p05_to_p1()
        elif gate_name in ("P1.5_to_P2", "GATE-P15-TO-P2"):
            return self.evaluate_p15_to_p2()
        elif gate_name == "auto":
            if not from_phase or not to_phase:
                raise ValueError("--from-phase and --to-phase required for auto gate")
            return self.evaluate_auto_gate(from_phase, to_phase)
        else:
            raise ValueError(f"Unknown gate: {gate_name}")


@click.command()
@click.option(
    "--gate",
    type=str,
    required=True,
    help="Gate to evaluate: P2_to_P3, P5_to_P6, P0.5_to_P1, P1.5_to_P2, or auto",
)
@click.option(
    "--workspace",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Path to project workspace",
)
@click.option(
    "--from-phase",
    type=str,
    default=None,
    help="Source phase for auto gate (e.g., P3)",
)
@click.option(
    "--to-phase",
    type=str,
    default=None,
    help="Target phase for auto gate (e.g., P4)",
)
def main(gate: str, workspace: Path, from_phase: Optional[str], to_phase: Optional[str]) -> None:
    """Evaluate gate conditions for phase transitions."""
    script_dir = Path(__file__).parent
    orchestration_dir = script_dir.parent / "orchestration"

    if not orchestration_dir.exists():
        click.echo(f"Error: orchestration directory not found at {orchestration_dir}", err=True)
        sys.exit(1)

    try:
        evaluator = GateEvaluator(workspace, orchestration_dir)
        result = evaluator.evaluate(gate, from_phase, to_phase)

        if result["result"] == "passed":
            exit_code = EXIT_PASSED
        elif result["result"] == "blocked":
            exit_code = EXIT_BLOCKED
        elif result["result"] == "needs_human_approval":
            exit_code = EXIT_HUMAN_APPROVAL
        else:
            exit_code = EXIT_BLOCKED

        if gate == "auto" and "exit_code" in result:
            exit_code = result["exit_code"]

        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(exit_code)

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
