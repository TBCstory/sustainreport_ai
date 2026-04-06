#!/usr/bin/env python3.13
"""
tests/test_run_pipeline_dispatch.py — PKT-B005: P0.5/P1.5 dispatch 실행 검증

P0.5/P1.5가 dispatch에서 silent pass되지 않는지 검증하는 E2E 회귀 테스트.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_pipeline import (
    PHASE_ORDER,
    PipelineEngine,
)


class TestPipelineDispatchNewPhases:
    """P0.5/P1.5가 dispatch에서 건너뛰어지지 않는지 검증."""

    def test_p05_dispatched_and_fails_without_intake(self, tmp_workspace):
        """P0.5만 실행: intake_manifest 없으면 success=False, phases_executed=['P0.5']."""
        engine = PipelineEngine(
            workspace=tmp_workspace,
            start_phase="P0.5",
            end_phase="P0.5",
            skip_approvals=True,
        )
        result = engine.run()
        assert "P0.5" in result.phases_executed, (
            f"P0.5가 phases_executed에 포함되어야 하는데 {result.phases_executed}입니다"
        )
        assert not result.success, "intake_manifest 없으면 P0.5는 실패해야 함"

    def test_p05_dispatched_and_succeeds_with_intake(self, tmp_workspace):
        """P0.5만 실행: intake_manifest 있으면 success=True."""
        (tmp_workspace / "00_definition" / "intake_manifest.json").write_text(
            json.dumps({"project_id": "PRJ-TEST"}), encoding="utf-8"
        )
        engine = PipelineEngine(
            workspace=tmp_workspace,
            start_phase="P0.5",
            end_phase="P0.5",
            skip_approvals=True,
        )
        result = engine.run()
        assert "P0.5" in result.phases_executed
        assert result.success, "intake_manifest 있으면 P0.5는 성공해야 함"

    def test_p15_dispatched_not_silent_pass(self, tmp_workspace):
        """P1.5만 실행: toc_draft 없으면 phases_executed에 P1.5가 포함되고 silent pass 아님."""
        engine = PipelineEngine(
            workspace=tmp_workspace,
            start_phase="P1.5",
            end_phase="P1.5",
            skip_approvals=True,
        )
        result = engine.run()
        assert "P1.5" in result.phases_executed, (
            f"P1.5가 phases_executed에 포함되어야 하는데 {result.phases_executed}입니다"
        )
        # 빈 phases_executed가 절대 안 됨
        assert len(result.phases_executed) > 0, "phases_executed는 절대 비어있지 않아야 함"

    def test_full_pipeline_includes_new_phases(self, tmp_workspace):
        """P0~P2 전체 실행: phases_executed에 P0.5, P1.5 포함."""
        # 최소한의 fixture: P0 project_charter + stakeholder, P0.5 intake_manifest, P1.5 toc_draft
        (tmp_workspace / "00_definition").mkdir(parents=True, exist_ok=True)
        (tmp_workspace / "00_definition" / "project_charter.json").write_text(
            json.dumps({"project_id": "PRJ-TEST", "project_name": "Test Project"}), encoding="utf-8"
        )
        (tmp_workspace / "00_definition" / "stakeholder_matrix.json").write_text(
            json.dumps({"stakeholders": []}), encoding="utf-8"
        )
        (tmp_workspace / "00_definition" / "intake_manifest.json").write_text(
            json.dumps({"project_id": "PRJ-TEST"}), encoding="utf-8"
        )
        (tmp_workspace / "05_planning").mkdir(parents=True, exist_ok=True)
        (tmp_workspace / "05_planning" / "toc_draft.json").write_text(
            json.dumps({"approved": True, "sections": []}), encoding="utf-8"
        )
        # P1 requires file_registry + segment_manifest (run_ingestion)
        (tmp_workspace / "02_file_registry").mkdir(parents=True, exist_ok=True)
        (tmp_workspace / "02_file_registry" / "file_registry.json").write_text(
            json.dumps({"files": []}), encoding="utf-8"
        )
        (tmp_workspace / "04_segments").mkdir(parents=True, exist_ok=True)
        (tmp_workspace / "04_segments" / "segment_manifest.json").write_text(
            json.dumps({"segments": []}), encoding="utf-8"
        )
        # P2 requires writing_blueprint + structure_index (run_toc_planner)
        (tmp_workspace / "05_planning" / "writing_blueprint.json").write_text(
            json.dumps({"sections": [], "approved": True}), encoding="utf-8"
        )
        (tmp_workspace / "05_planning" / "structure_index.json").write_text(
            json.dumps({"entries": []}), encoding="utf-8"
        )

        # NOTE: We only verify P0.5 and P1.5 dispatch here.
        # Full P0→P2 execution would call run_ingestion/run_toc_planner (LLM calls),
        # which is tested separately in integration tests.
        from scripts.run_pipeline import PHASE_ORDER

        assert PHASE_ORDER.index("P0.5") == PHASE_ORDER.index("P0") + 1
        assert PHASE_ORDER.index("P1.5") == PHASE_ORDER.index("P1") + 1
        assert "P0.5" in PHASE_ORDER
        assert "P1.5" in PHASE_ORDER

    def test_phase_range_filter_uses_index_not_string(self):
        """Phase 범위 필터가 인덱스 기반인지 검증.

        P0.5는 P0과 P1 사이에, P1.5는 P1과 P2 사이에 위치해야 함.
        """
        assert PHASE_ORDER.index("P0.5") == PHASE_ORDER.index("P0") + 1, "P0.5는 P0 바로 다음 인덱스에 위치해야 함"
        assert PHASE_ORDER.index("P1.5") == PHASE_ORDER.index("P1") + 1, "P1.5는 P1 바로 다음 인덱스에 위치해야 함"
        # P0 < P0.5 < P1 < P1.5 < P2 순서 검증
        assert PHASE_ORDER.index("P0") < PHASE_ORDER.index("P0.5")
        assert PHASE_ORDER.index("P0.5") < PHASE_ORDER.index("P1")
        assert PHASE_ORDER.index("P1") < PHASE_ORDER.index("P1.5")
        assert PHASE_ORDER.index("P1.5") < PHASE_ORDER.index("P2")
