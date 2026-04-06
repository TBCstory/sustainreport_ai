#!/usr/bin/env python3.13
"""
tests/test_workspace_doctor.py

PKT-B006: workspace doctor tests
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.workspace_doctor import (
    CheckResult,
    check_gate_consistency,
    check_meta_field_names,
    check_next_actions_stale,
    check_open_queries,
    check_phase_consistency,
    compute_current_phase,
    main,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


# ── tests ────────────────────────────────────────────────────────────────────


class TestComputeCurrentPhase:
    def _ws(self, tmp_path: Path) -> Path:
        # minimal skeleton
        for d in (
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
        ):
            (tmp_path / d).mkdir()
        return tmp_path

    def test_no_artifacts_yields_p0(self, tmp_path: Path):
        ws = self._ws(tmp_path)
        assert compute_current_phase(ws) == "P0"

    def test_only_charter_and_stakeholder_yields_p0_5(self, tmp_path: Path):
        ws = self._ws(tmp_path)
        write_json(ws / "00_definition/project_charter.json", {"title": "test"})
        write_json(ws / "00_definition/stakeholder_matrix.json", {"stakeholders": []})
        assert compute_current_phase(ws) == "P0.5"

    def test_p1_artifacts_present_yields_p1_5(self, tmp_path: Path):
        ws = self._ws(tmp_path)
        write_json(ws / "00_definition/project_charter.json", {"title": "t"})
        write_json(ws / "00_definition/stakeholder_matrix.json", {"s": []})
        write_json(ws / "00_definition/intake_manifest.json", {"custom_toc_reference": {}})
        write_json(ws / "02_file_registry/file_registry.json", {"files": []})
        write_json(ws / "04_segments/segment_manifest.json", {"segments": []})
        write_json(ws / "05_planning/toc_draft.json", {"sections": []})
        write_json(ws / "approval_gates.json", {"gates": {"P1.5_to_P2": {"status": "approved"}}})
        # P1.5 complete → current_phase is next phase P2
        assert compute_current_phase(ws) == "P2"

    def test_draft_meta_files_present_yields_p4(self, tmp_path: Path):
        ws = self._ws(tmp_path)
        write_json(ws / "00_definition/project_charter.json", {"title": "t"})
        write_json(ws / "00_definition/stakeholder_matrix.json", {"s": []})
        write_json(ws / "00_definition/intake_manifest.json", {"custom_toc_reference": {}})
        write_json(ws / "02_file_registry/file_registry.json", {"files": []})
        write_json(ws / "04_segments/segment_manifest.json", {"segments": []})
        write_json(ws / "05_planning/toc_draft.json", {"sections": []})
        write_json(ws / "05_planning/writing_blueprint.json", {"sections": []})
        write_json(ws / "05_planning/structure_index.json", {"index": []})
        write_json(
            ws / "approval_gates.json",
            {
                "gates": {
                    "P1.5_to_P2": {"status": "approved"},
                    "P2_to_P3": {"status": "approved"},
                }
            },
        )
        # P3 buckets
        (ws / "06_buckets/SEC-1.json").write_text("{}")
        # P4 drafts
        write_json(ws / "07_drafts/SEC-1_meta.json", {"section_id": "SEC-1"})
        # P4 complete → current_phase is next phase P5
        assert compute_current_phase(ws) == "P5"


class TestCheckPhaseConsistency:
    def test_matching_state_passes(self, tmp_path: Path):
        ws = tmp_path
        (ws / "00_definition").mkdir()
        write_json(ws / "00_definition/project_charter.json", {"title": "t"})
        write_json(ws / "00_definition/stakeholder_matrix.json", {"s": []})
        # current_phase=P0.5 matches computed
        write_json(ws / "project_state.json", {"current_phase": "P0.5"})
        r = check_phase_consistency(ws)
        assert r.status == "pass"

    def test_mismatched_state_warns(self, tmp_path: Path):
        ws = tmp_path
        (ws / "00_definition").mkdir()
        write_json(ws / "00_definition/project_charter.json", {"title": "t"})
        write_json(ws / "00_definition/stakeholder_matrix.json", {"s": []})
        # state says P2 but only P0.5 done
        write_json(ws / "project_state.json", {"current_phase": "P2"})
        r = check_phase_consistency(ws)
        assert r.status == "warning"
        assert "P2" in r.details and "P0.5" in r.details

    def test_missing_state_file_errors(self, tmp_path: Path):
        ws = tmp_path
        (ws / "00_definition").mkdir()
        write_json(ws / "00_definition/project_charter.json", {"title": "t"})
        write_json(ws / "00_definition/stakeholder_matrix.json", {"s": []})
        # no project_state.json at all
        r = check_phase_consistency(ws)
        assert r.status == "error"


class TestCheckGateConsistency:
    def test_approved_gate_missing_prereq_warns(self, tmp_path: Path):
        ws = tmp_path
        (ws / "05_planning").mkdir()
        write_json(
            ws / "approval_gates.json",
            {"gates": {"P2_to_P3": {"status": "approved", "gate_name": "P2_to_P3"}}},
        )
        # writing_blueprint.json missing
        r = check_gate_consistency(ws)
        assert r.status == "warning"
        assert "P2_to_P3" in r.details and "writing_blueprint.json" in r.details

    def test_waiting_gate_with_all_prereqs_warns(self, tmp_path: Path):
        ws = tmp_path
        (ws / "05_planning").mkdir()
        write_json(
            ws / "approval_gates.json",
            {"gates": {"P2_to_P3": {"status": "waiting", "gate_name": "P2_to_P3"}}},
        )
        write_json(ws / "05_planning/writing_blueprint.json", {"sections": []})
        write_json(ws / "05_planning/structure_index.json", {"index": []})
        r = check_gate_consistency(ws)
        assert r.status == "warning"
        assert "waiting" in r.details

    def test_consistent_gates_pass(self, tmp_path: Path):
        ws = tmp_path
        (ws / "05_planning").mkdir()
        write_json(
            ws / "approval_gates.json",
            {"gates": {"P2_to_P3": {"status": "approved", "gate_name": "P2_to_P3"}}},
        )
        write_json(ws / "05_planning/writing_blueprint.json", {"sections": []})
        write_json(ws / "05_planning/structure_index.json", {"index": []})
        r = check_gate_consistency(ws)
        assert r.status == "pass"


class TestCheckMetaFieldNames:
    def test_normalized_fields_pass(self, tmp_path: Path):
        ws = tmp_path
        (ws / "07_drafts").mkdir()
        write_json(
            ws / "07_drafts/SEC-1_meta.json",
            {
                "section_id": "SEC-1",
                "heading_ko": "환경 정책",
                "draft_confidence": 0.75,
                "evidence_segments": [],
                "placeholders": [],
                "missing_evidence": [],
            },
        )
        r = check_meta_field_names(ws)
        assert r.status == "pass"

    def test_legacy_heading_text_warns(self, tmp_path: Path):
        ws = tmp_path
        (ws / "07_drafts").mkdir()
        write_json(
            ws / "07_drafts/SEC-2_meta.json",
            {
                "section_id": "SEC-2",
                "heading_text": "노동안정관계",  # legacy
                "confidence": 0.6,  # legacy
            },
        )
        r = check_meta_field_names(ws)
        assert r.status == "warning"
        assert "heading_text" in r.details or "legacy" in r.details.lower()

    def test_no_drafts_dir_warns(self, tmp_path: Path):
        ws = tmp_path
        r = check_meta_field_names(ws)
        # 07_drafts/ missing → warning (not an error)
        assert r.status == "warning"


class TestCheckNextActionsStale:
    def test_missing_file_warns(self, tmp_path: Path):
        ws = tmp_path
        r = check_next_actions_stale(ws)
        assert r.status == "warning"

    def test_no_updated_at_field_warns(self, tmp_path: Path):
        ws = tmp_path
        (ws / "next_actions.json").write_text("{}")
        r = check_next_actions_stale(ws)
        assert r.status == "warning"


class TestCheckOpenQueries:
    def test_no_draft_queries_file_warns(self, tmp_path: Path):
        ws = tmp_path
        r = check_open_queries(ws)
        assert r.status == "warning"

    def test_no_open_queries_passes(self, tmp_path: Path):
        ws = tmp_path
        write_json(ws / "draft_queries.json", {"queries": []})
        r = check_open_queries(ws)
        assert r.status == "pass"

    def test_open_query_conflict_warns(self, tmp_path: Path):
        ws = tmp_path
        write_json(
            ws / "draft_queries.json",
            {"queries": [{"id": "DQ-001", "status": "open", "section_id": "SEC-1"}]},
        )
        write_json(
            ws / "project_state.json",
            {
                "current_phase": "P5",
                "section_progress": {"SEC-1": {"status": "approved"}},
            },
        )
        r = check_open_queries(ws)
        assert r.status == "warning"
        assert "DQ-001" in r.details


class TestMain:
    def test_check_mode_exit_0_on_clean(self, tmp_path: Path):
        ws = tmp_path
        (ws / "00_definition").mkdir()
        write_json(ws / "00_definition/project_charter.json", {"title": "t"})
        write_json(ws / "00_definition/stakeholder_matrix.json", {"s": []})
        write_json(ws / "project_state.json", {"current_phase": "P0.5"})
        write_json(ws / "approval_gates.json", {"gates": {}})
        write_json(ws / "next_actions.json", {"updated_at": "2099-01-01T00:00:00Z"})
        write_json(ws / "draft_queries.json", {"queries": []})
        (ws / "07_drafts").mkdir()
        write_json(
            ws / "07_drafts/SEC-1_meta.json",
            {
                "heading_ko": "t",
                "draft_confidence": 0.5,
                "evidence_segments": [],
                "placeholders": [],
                "missing_evidence": [],
            },
        )
        exit_code = main(["--workspace", str(ws)])
        assert exit_code == 0

    def test_check_mode_exit_1_on_warning(self, tmp_path: Path):
        ws = tmp_path
        write_json(ws / "project_state.json", {"current_phase": "P9"})
        exit_code = main(["--workspace", str(ws)])
        assert exit_code == 1

    def test_json_output_is_valid(self, tmp_path: Path):
        ws = tmp_path
        write_json(ws / "project_state.json", {"current_phase": "P0"})
        write_json(ws / "approval_gates.json", {"gates": {}})
        out = sys.stdout
        import io

        captured = io.StringIO()
        sys.stdout = captured
        try:
            main(["--workspace", str(ws), "--json"])
        finally:
            sys.stdout = out
        data = json.loads(captured.getvalue())
        assert "workspace" in data
        assert "checks" in data
        assert "summary" in data
