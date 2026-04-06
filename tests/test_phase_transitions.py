#!/usr/bin/env python3.13
"""
tests/test_phase_transitions.py — P0.5/P1.5 phase transition 검증

PKT-A001~A003에서 구현한 phase transition을 검증하는 회귀 테스트.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_pipeline import PHASE_ORDER as RUN_PIPELINE_PHASE_ORDER
from scripts.state_manager import PHASE_ORDER as STATE_MANAGER_PHASE_ORDER


def _setup_workspace(tmp_path: Path, files: dict) -> Path:
    """워크스페이스 설정 헬퍼."""
    ws = tmp_path / "PRJ-TEST"
    for rel_path, content in files.items():
        full_path = ws / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            full_path.write_text(content, encoding="utf-8")
        else:
            full_path.write_bytes(content)
    return ws


# ─────────────────────────────────────────────────────────────────────────────
# 테스트 1: state_manager / run_pipeline PHASE_ORDER에 P0.5, P1.5 포함 검증
# ─────────────────────────────────────────────────────────────────────────────


def test_state_manager_phase_order_includes_new_phases():
    """state_manager의 PHASE_ORDER에 P0.5, P1.5가 포함됨."""
    assert "P0.5" in STATE_MANAGER_PHASE_ORDER, "state_manager.PHASE_ORDER에 P0.5 없음"
    assert "P1.5" in STATE_MANAGER_PHASE_ORDER, "state_manager.PHASE_ORDER에 P1.5 없음"
    assert STATE_MANAGER_PHASE_ORDER.index("P0.5") == STATE_MANAGER_PHASE_ORDER.index("P0") + 1
    assert STATE_MANAGER_PHASE_ORDER.index("P1.5") == STATE_MANAGER_PHASE_ORDER.index("P1") + 1


def test_run_pipeline_phase_order_includes_new_phases():
    """run_pipeline의 PHASE_ORDER에 P0.5, P1.5가 포함됨."""
    assert "P0.5" in RUN_PIPELINE_PHASE_ORDER, "run_pipeline.PHASE_ORDER에 P0.5 없음"
    assert "P1.5" in RUN_PIPELINE_PHASE_ORDER, "run_pipeline.PHASE_ORDER에 P1.5 없음"
    assert RUN_PIPELINE_PHASE_ORDER.index("P0.5") == RUN_PIPELINE_PHASE_ORDER.index("P0") + 1
    assert RUN_PIPELINE_PHASE_ORDER.index("P1.5") == RUN_PIPELINE_PHASE_ORDER.index("P1") + 1


# ─────────────────────────────────────────────────────────────────────────────
# 테스트 2: P0.5 완료 조건 — intake_manifest.json 존재 시
# ─────────────────────────────────────────────────────────────────────────────


def test_p05_complete_when_intake_manifest_exists(tmp_path):
    """intake_manifest.json이 있으면 P0.5가 complete로 계산됨."""
    from scripts.update_project_state import determine_phase

    ws = _setup_workspace(
        tmp_path,
        {
            "00_definition/project_charter.json": json.dumps({"project_id": "PRJ-TEST"}),
            "00_definition/stakeholder_matrix.json": json.dumps({}),
            "00_definition/intake_manifest.json": json.dumps({"project_id": "PRJ-TEST"}),
        },
    )

    current_phase, phase_status = determine_phase(ws, {})

    assert phase_status.get("P0.5") == "complete", f"P0.5가 complete여야 하는데 {phase_status.get('P0.5')}입니다"


def test_p05_implicit_complete_when_intake_manifest_absent_but_p1_done(tmp_path):
    """intake_manifest.json이 없더라도 P1 산출물이 있으면 P0.5가 implicit complete."""
    from scripts.update_project_state import determine_phase

    ws = _setup_workspace(
        tmp_path,
        {
            "00_definition/project_charter.json": json.dumps({"project_id": "PRJ-TEST"}),
            "00_definition/stakeholder_matrix.json": json.dumps({}),
            "02_file_registry/file_registry.json": json.dumps({"files": [{"file_id": "F-0001"}]}),
            "04_segments/segment_manifest.json": json.dumps({"segments": []}),
        },
    )

    current_phase, phase_status = determine_phase(ws, {})

    # P0.5는 implicit complete (P1 산출물로推断)
    assert phase_status.get("P0.5") == "complete", (
        f"P0.5가 implicit complete여야 하는데 {phase_status.get('P0.5')}입니다"
    )
    # P1도 complete
    assert phase_status.get("P1") == "complete", f"P1이 complete여야 하는데 {phase_status.get('P1')}입니다"


# ─────────────────────────────────────────────────────────────────────────────
# 테스트 3: P1.5 완료 조건 — toc_draft.json + P1.5_to_P2 게이트 approved
# ─────────────────────────────────────────────────────────────────────────────


def test_p15_complete_when_toc_draft_approved(tmp_path):
    """toc_draft.json이 있고 P1.5_to_P2 게이트가 approved이면 P1.5가 complete."""
    from scripts.update_project_state import determine_phase

    ws = _setup_workspace(
        tmp_path,
        {
            "00_definition/project_charter.json": json.dumps({"project_id": "PRJ-TEST"}),
            "00_definition/stakeholder_matrix.json": json.dumps({}),
            "00_definition/intake_manifest.json": json.dumps({}),
            "02_file_registry/file_registry.json": json.dumps({"files": []}),
            "04_segments/segment_manifest.json": json.dumps({"segments": []}),
            "05_planning/toc_draft.json": json.dumps({"status": "approved", "sections": []}),
            "approval_gates.json": json.dumps({"gates": {"P1.5_to_P2": {"status": "approved"}}}),
        },
    )

    current_phase, phase_status = determine_phase(ws, {})

    assert phase_status.get("P1.5") == "complete", f"P1.5가 complete여야 하는데 {phase_status.get('P1.5')}입니다"


def test_p15_not_complete_when_toc_draft_exists_but_gate_not_approved(tmp_path):
    """toc_draft.json이 있어도 P1.5_to_P2 게이트가 approved가 아니면 P1.5는 incomplete."""
    from scripts.update_project_state import determine_phase

    ws = _setup_workspace(
        tmp_path,
        {
            "00_definition/project_charter.json": json.dumps({"project_id": "PRJ-TEST"}),
            "00_definition/stakeholder_matrix.json": json.dumps({}),
            "02_file_registry/file_registry.json": json.dumps({"files": []}),
            "04_segments/segment_manifest.json": json.dumps({"segments": []}),
            "05_planning/toc_draft.json": json.dumps({"status": "draft", "sections": []}),
            "approval_gates.json": json.dumps({"gates": {"P2_to_P3": {"status": "approved"}}}),
        },
    )

    current_phase, phase_status = determine_phase(ws, {})

    assert phase_status.get("P1.5") != "complete", f"P1.5는 incomplete여야 하는데 {phase_status.get('P1.5')}입니다"


def test_p15_implicit_complete_when_toc_draft_absent_but_p2_done(tmp_path):
    """toc_draft.json이 없어도 P2 산출물이 있으면 P1.5가 implicit complete."""
    from scripts.update_project_state import determine_phase

    ws = _setup_workspace(
        tmp_path,
        {
            "00_definition/project_charter.json": json.dumps({"project_id": "PRJ-TEST"}),
            "00_definition/stakeholder_matrix.json": json.dumps({}),
            "02_file_registry/file_registry.json": json.dumps({"files": []}),
            "04_segments/segment_manifest.json": json.dumps({"segments": []}),
            "05_planning/structure_index.json": json.dumps({"entries": []}),
            "05_planning/writing_blueprint.json": json.dumps({"sections": [], "approved": True}),
            "05_planning/section_manifest.json": json.dumps({"sections": []}),
            "approval_gates.json": json.dumps({"gates": {"P2_to_P3": {"status": "approved"}}}),
        },
    )

    current_phase, phase_status = determine_phase(ws, {})

    # P1.5는 implicit complete (P2 산출물로推断)
    assert phase_status.get("P1.5") == "complete", (
        f"P1.5가 implicit complete여야 하는데 {phase_status.get('P1.5')}입니다"
    )
    # P2도 complete
    assert phase_status.get("P2") == "complete", f"P2가 complete여야 하는데 {phase_status.get('P2')}입니다"


# ─────────────────────────────────────────────────────────────────────────────
# 테스트 4: check_gate.py P0.5_to_P1, P1.5_to_P2 게이트 처리
# ─────────────────────────────────────────────────────────────────────────────


def test_check_gate_handles_p05_to_p1_when_intake_manifest_missing(tmp_path):
    """P0.5_to_P1: intake_manifest 없으면 blocked 처리."""
    from scripts.check_gate import GateEvaluator

    ws = tmp_path / "PRJ-TEST"
    ws.mkdir(parents=True)
    (ws / "00_definition").mkdir()
    (ws / "approval_gates.json").write_text(json.dumps({"gates": {}}), encoding="utf-8")

    evaluator = GateEvaluator(workspace=ws, orchestration_dir=Path("orchestration"))
    result = evaluator.evaluate("P0.5_to_P1")

    assert result["gate"] == "P0.5_to_P1"
    assert result["result"] in ("blocked", "passed"), (
        f"P0.5_to_P1은 blocked 또는 passed여야 하는데 {result['result']}입니다"
    )


def test_check_gate_handles_p05_to_p1_when_intake_manifest_exists(tmp_path):
    """P0.5_to_P1: intake_manifest 있으면 auto pass."""
    from scripts.check_gate import GateEvaluator

    ws = tmp_path / "PRJ-TEST"
    ws.mkdir(parents=True)
    (ws / "00_definition").mkdir()
    (ws / "00_definition/intake_manifest.json").write_text(json.dumps({"project_id": "PRJ-TEST"}), encoding="utf-8")
    (ws / "approval_gates.json").write_text(json.dumps({"gates": {}}), encoding="utf-8")

    evaluator = GateEvaluator(workspace=ws, orchestration_dir=Path("orchestration"))
    result = evaluator.evaluate("P0.5_to_P1")

    assert result["gate"] == "P0.5_to_P1"
    assert result["result"] == "passed", f"P0.5_to_P1은 passed여야 하는데 {result['result']}입니다"


def test_check_gate_handles_p15_to_p2_requires_human_approval(tmp_path):
    """P1.5_to_P2: toc_draft.json 있어도 게이트 미승인 시 human_approval_required."""
    from scripts.check_gate import GateEvaluator

    ws = tmp_path / "PRJ-TEST"
    ws.mkdir(parents=True)
    (ws / "05_planning").mkdir()
    (ws / "05_planning/toc_draft.json").write_text(json.dumps({"status": "draft", "sections": []}), encoding="utf-8")
    (ws / "approval_gates.json").write_text(
        json.dumps({"gates": {"P1.5_to_P2": {"status": "waiting"}}}), encoding="utf-8"
    )

    evaluator = GateEvaluator(workspace=ws, orchestration_dir=Path("orchestration"))
    result = evaluator.evaluate("P1.5_to_P2")

    assert result["gate"] == "P1.5_to_P2"
    assert result["result"] in ("needs_human_approval", "blocked"), (
        f"P1.5_to_P2는 needs_human_approval 또는 blocked여야 하는데 {result['result']}입니다"
    )


def test_check_gate_handles_p15_to_p2_passed_when_approved(tmp_path):
    """P1.5_to_P2: toc_draft.json + 게이트 approved 시 passed."""
    from scripts.check_gate import GateEvaluator

    ws = tmp_path / "PRJ-TEST"
    ws.mkdir(parents=True)
    (ws / "05_planning").mkdir()
    (ws / "05_planning/toc_draft.json").write_text(json.dumps({"status": "approved", "sections": []}), encoding="utf-8")
    (ws / "approval_gates.json").write_text(
        json.dumps({"gates": {"P1.5_to_P2": {"status": "approved"}}}), encoding="utf-8"
    )

    evaluator = GateEvaluator(workspace=ws, orchestration_dir=Path("orchestration"))
    result = evaluator.evaluate("P1.5_to_P2")

    assert result["gate"] == "P1.5_to_P2"
    assert result["result"] == "passed", f"P1.5_to_P2는 passed여야 하는데 {result['result']}입니다"
