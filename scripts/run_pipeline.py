#!/usr/bin/env python3.13
"""
run_pipeline.py — P0→P7 파이프라인 실행 엔진

역할:
1. Phase 순차 실행 (P0→P1→P2→...→P7)
2. 게이트 조건 확인 (check_gate.py 연동)
3. 상태 추적 (state_manager.py 연동)
4. 섹션별 병렬 실행 (run_section_writer.py)

사용법:
    # 전체 파이프라인
    uv run python scripts/run_pipeline.py --workspace workspaces/PRJ-2026-CLNT-001

    # P2부터 P5까지
    uv run python scripts/run_pipeline.py --workspace ... --start-phase P2 --end-phase P5

    # 테스트 모드 (게이트 스킵)
    uv run python scripts/run_pipeline.py --workspace ... --skip-approvals
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.check_gate import GateEvaluator
from scripts.log_event import ensure_context_bus
from scripts.rebuild_summaries import rebuild_blocking_issues, rebuild_next_actions
from scripts.state_manager import StateManager

# ─────────────────────────────────────────────────────────────────────────────
# Phase 순서 및 매핑
# ─────────────────────────────────────────────────────────────────────────────

PHASE_ORDER = ["P0", "P0.5", "P1", "P1.5", "P2", "P3", "P4", "P5", "P6", "P7"]

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

# ─────────────────────────────────────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PhaseResult:
    """Phase 실행 결과."""

    phase: str
    success: bool
    duration_seconds: float = 0.0
    message: str = ""
    outputs: list[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class PipelineResult:
    """파이프라인 전체 실행 결과."""

    success: bool
    phases_executed: list[str] = field(default_factory=list)
    phases_completed: list[PhaseResult] = field(default_factory=list)
    phases_blocked: list[PhaseResult] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    blocked_at: Optional[str] = None
    error: Optional[str] = None


class PipelineBlockedError(Exception):
    """파이프라인이 게이트에서 차단됨."""

    def __init__(self, gate_name: str, reason: str, can_override: bool = False):
        self.gate_name = gate_name
        self.reason = reason
        self.can_override = can_override
        super().__init__(f"Pipeline blocked at {gate_name}: {reason}")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 실행 래퍼 ( импорт from individual phase scripts )
# ─────────────────────────────────────────────────────────────────────────────


def _run_phase_p0_5(workspace: Path) -> PhaseResult:
    """P0.5: 인테이크 인터뷰 — intake_manifest.json 존재 확인."""
    start = time.monotonic()
    intake = workspace / "00_definition" / "intake_manifest.json"
    duration = time.monotonic() - start
    if intake.exists():
        return PhaseResult(
            phase="P0.5",
            success=True,
            duration_seconds=duration,
            message="P0.5 완료: intake_manifest.json 확인됨.",
            outputs=[str(intake.relative_to(workspace))],
        )
    else:
        return PhaseResult(
            phase="P0.5",
            success=False,
            duration_seconds=duration,
            message="P0.5 차단: intake_manifest.json 미생성. 인테이크 인터뷰를 먼저 수행하세요.",
            outputs=[],
        )


def _run_phase_p1_5(workspace: Path) -> PhaseResult:
    """P1.5: 목차 논의 — toc_draft.json 생성 또는 존재 확인."""
    start = time.monotonic()
    toc_draft = workspace / "05_planning" / "toc_draft.json"

    if toc_draft.exists():
        duration = time.monotonic() - start
        return PhaseResult(
            phase="P1.5",
            success=True,
            duration_seconds=duration,
            message="P1.5 완료: toc_draft.json 확인됨.",
            outputs=[str(toc_draft.relative_to(workspace))],
        )

    # toc_draft 미존재 → 생성 시도
    try:
        from scripts.run_toc_planner import run_toc_draft

        result = run_toc_draft(workspace)
        duration = time.monotonic() - start

        if result.get("success"):
            outputs = result.get("outputs", [])
            msg = "P1.5 완료: toc_draft.json 생성됨."
            if result.get("waiting"):
                msg = f"P1.5 대기: {result.get('gate_name', 'P1.5_to_P2')} 승인 대기 중."
            return PhaseResult(
                phase="P1.5",
                success=True,
                duration_seconds=duration,
                message=msg,
                outputs=outputs,
            )
        else:
            return PhaseResult(
                phase="P1.5",
                success=False,
                duration_seconds=duration,
                message=f"P1.5 실패: {result.get('message', 'toc_draft 생성 실패')}",
                outputs=[],
            )
    except Exception as e:
        duration = time.monotonic() - start
        return PhaseResult(
            phase="P1.5",
            success=False,
            duration_seconds=duration,
            message=f"P1.5 차단: toc_draft.json 미생성. run_toc_planner.py --toc-draft 실행 필요. ({e})",
            outputs=[],
        )


def _run_phase_p0(workspace: Path) -> PhaseResult:
    """P0: 프로젝트 정의 — 00_definition/ 파일 생성 확인."""
    start = time.monotonic()
    outputs = []

    charter = workspace / "00_definition" / "project_charter.json"
    stakeholder = workspace / "00_definition" / "stakeholder_matrix.json"

    if charter.exists():
        outputs.append(str(charter.relative_to(workspace)))
    if stakeholder.exists():
        outputs.append(str(stakeholder.relative_to(workspace)))

    success = charter.exists() and stakeholder.exists()
    duration = time.monotonic() - start

    return PhaseResult(
        phase="P0",
        success=success,
        duration_seconds=round(duration, 2),
        message="프로젝트 정의 완료" if success else "project_charter.json 또는 stakeholder_matrix.json 미존재",
        outputs=outputs,
    )


def _run_phase_p1(workspace: Path, state_manager: StateManager) -> PhaseResult:
    """P1: 자료 투입 — 정규화 + 세그먼트 추출."""
    start = time.monotonic()
    outputs = []

    try:
        from scripts.run_ingestion import run_ingestion

        # 01_raw/ 에서 파일 목록 수집
        raw_dir = workspace / "01_raw"
        file_paths = []
        if raw_dir.is_dir():
            for ext in (".pdf", ".docx", ".hwp", ".txt", ".md", ".xlsx", ".csv"):
                file_paths.extend(raw_dir.rglob(f"*{ext}"))

        result = run_ingestion(workspace=str(workspace), file_paths=[str(f) for f in file_paths])
        outputs = result.get("outputs", [])

        # file_registry, segment_manifest 존재 확인
        registry = workspace / "02_file_registry" / "file_registry.json"
        segment_mf = workspace / "04_segments" / "segment_manifest.json"

        success = registry.exists() and segment_mf.exists()
        message = f"P1 완료: {len(outputs)}개 파일 처리" if success else "file_registry 또는 segment_manifest 미생성"

    except ImportError:
        # run_ingestion.py가 없으면 파일 존재만 확인
        registry = workspace / "02_file_registry" / "file_registry.json"
        segment_mf = workspace / "04_segments" / "segment_manifest.json"
        success = registry.exists() and segment_mf.exists()
        message = "P1 완료 (run_ingestion.py 미설치)" if success else "P1 산출물 미존재"

        if registry.exists():
            outputs.append(str(registry.relative_to(workspace)))
        if segment_mf.exists():
            outputs.append(str(segment_mf.relative_to(workspace)))

    duration = time.monotonic() - start
    return PhaseResult(
        phase="P1",
        success=success,
        duration_seconds=round(duration, 2),
        message=message,
        outputs=outputs,
    )


def _run_phase_p2(workspace: Path, state_manager: StateManager, skip_approvals: bool = False) -> PhaseResult:
    """P2: 기획 — writing_blueprint 생성."""
    start = time.monotonic()
    outputs = []

    try:
        from scripts.run_toc_planner import run_toc_planner

        result = run_toc_planner(
            workspace=str(workspace),
            state_manager=state_manager,
            skip_approval=skip_approvals,
        )
        outputs = result.get("outputs", [])

        # Respect run_toc_planner's success flag — if approval timed out or was rejected,
        # result["success"] will be False even though files may exist.
        # This ensures the pipeline correctly marks the phase as failed.
        planner_success = result.get("success", False)
        blueprint = workspace / "05_planning" / "writing_blueprint.json"
        structure = workspace / "05_planning" / "structure_index.json"
        success = planner_success and blueprint.exists() and structure.exists()
        message = (
            result.get("message", "") or f"P2 완료: blueprint={blueprint.exists()}, structure={structure.exists()}"
        )

    except ImportError:
        blueprint = workspace / "05_planning" / "writing_blueprint.json"
        structure = workspace / "05_planning" / "structure_index.json"
        success = blueprint.exists() and structure.exists()
        message = "P2 완료 (run_toc_planner.py 미설치)" if success else "writing_blueprint 또는 structure_index 미존재"

        if blueprint.exists():
            outputs.append(str(blueprint.relative_to(workspace)))
        if structure.exists():
            outputs.append(str(structure.relative_to(workspace)))

    duration = time.monotonic() - start
    return PhaseResult(
        phase="P2",
        success=success,
        duration_seconds=round(duration, 2),
        message=message,
        outputs=outputs,
    )


def _run_phase_p3(workspace: Path, state_manager: StateManager) -> PhaseResult:
    """P3: 버킷 구축 — 섹션별 버킷 JSON 생성."""
    start = time.monotonic()
    outputs = []

    try:
        from scripts.run_framework_mapper import run_framework_mapper

        result = run_framework_mapper(workspace=str(workspace))
        outputs = result.get("outputs", [])

        # 버킷 파일 존재 확인
        buckets_dir = workspace / "06_buckets"
        bucket_files = list(buckets_dir.glob("SEC-*.json")) if buckets_dir.is_dir() else []
        success = len(bucket_files) > 0
        message = f"P3 완료: {len(bucket_files)}개 버킷 생성" if success else "버킷 파일 미생성"

    except ImportError:
        buckets_dir = workspace / "06_buckets"
        bucket_files = list(buckets_dir.glob("SEC-*.json")) if buckets_dir.is_dir() else []
        success = len(bucket_files) > 0
        message = (
            f"P3 완료 (run_framework_mapper.py 미설치): {len(bucket_files)}개 버킷" if success else "버킷 파일 미존재"
        )
        outputs = [str(f.relative_to(workspace)) for f in bucket_files]

    duration = time.monotonic() - start
    return PhaseResult(
        phase="P3",
        success=success,
        duration_seconds=round(duration, 2),
        message=message,
        outputs=outputs,
    )


def _run_phase_p4(
    workspace: Path,
    state_manager: StateManager,
    parallel_sections: bool = True,
    section_ids: Optional[list[str]] = None,
) -> PhaseResult:
    """P4: 초안 작성 — 섹션별 초안 MD + meta JSON 생성."""
    start = time.monotonic()
    outputs = []

    try:
        from scripts.run_section_writer import run_section_writer

        result = run_section_writer(
            workspace=str(workspace),
            section_ids=section_ids,
            parallel=parallel_sections,
        )
        outputs = result.get("outputs", [])

        # draft meta 파일 존재 확인
        drafts_dir = workspace / "07_drafts"
        draft_metas = list(drafts_dir.glob("SEC-*_meta.json")) if drafts_dir.is_dir() else []
        success = len(draft_metas) > 0
        message = f"P4 완료: {len(draft_metas)}개 섹션 초안" if success else "초안 파일 미생성"

    except ImportError:
        drafts_dir = workspace / "07_drafts"
        draft_metas = list(drafts_dir.glob("SEC-*_meta.json")) if drafts_dir.is_dir() else []
        success = len(draft_metas) > 0
        message = (
            f"P4 완료 (run_section_writer.py 미설치): {len(draft_metas)}개 초안" if success else "초안 파일 미존재"
        )
        outputs = [str(f.relative_to(workspace)) for f in draft_metas]

    duration = time.monotonic() - start
    return PhaseResult(
        phase="P4",
        success=success,
        duration_seconds=round(duration, 2),
        message=message,
        outputs=outputs,
    )


def _run_phase_p5(workspace: Path, state_manager: StateManager) -> PhaseResult:
    """P5: 검수 — 내부 검수 + 팩트체크."""
    start = time.monotonic()
    outputs = []

    # 내부 검수
    try:
        from scripts.run_internal_reviewer import run_internal_reviewer

        result_ir = run_internal_reviewer(workspace=str(workspace))
        outputs.extend(result_ir.get("outputs", []))
    except ImportError:
        internal_report = workspace / "08_review" / "internal_review_report.json"
        if internal_report.exists():
            outputs.append(str(internal_report.relative_to(workspace)))

    # 팩트체크
    try:
        from scripts.run_fact_checker import run_fact_checker

        result_fc = run_fact_checker(workspace=str(workspace))
        outputs.extend(result_fc.get("outputs", []))
    except ImportError:
        fact_check = workspace / "08_review" / "fact_check_report.json"
        if fact_check.exists():
            outputs.append(str(fact_check.relative_to(workspace)))

    internal_report = workspace / "08_review" / "internal_review_report.json"
    fact_check = workspace / "08_review" / "fact_check_report.json"
    success = internal_report.exists() and fact_check.exists()
    message = "P5 완료: 검수 + 팩트체크" if success else "검수 보고서 미생성"

    duration = time.monotonic() - start
    return PhaseResult(
        phase="P5",
        success=success,
        duration_seconds=round(duration, 2),
        message=message,
        outputs=outputs,
    )


def _run_phase_p6(workspace: Path, state_manager: StateManager) -> PhaseResult:
    """P6: 초안 정리 및 핸드오프."""
    start = time.monotonic()
    outputs = []

    try:
        from scripts.run_handoff import run_handoff

        result = run_handoff(workspace=str(workspace))
        outputs = result.get("outputs", [])

        handoff_pkg = workspace / "09_handoff" / "draft_package.json"
        success = handoff_pkg.exists()
        message = "P6 완료: 핸드오프 패키지 생성" if success else "draft_package.json 미생성"

    except ImportError:
        handoff_pkg = workspace / "09_handoff" / "draft_package.json"
        success = handoff_pkg.exists()
        message = "P6 완료 (run_handoff.py 미설치)" if success else "핸드오프 패키지 미존재"
        if handoff_pkg.exists():
            outputs.append(str(handoff_pkg.relative_to(workspace)))

    duration = time.monotonic() - start
    return PhaseResult(
        phase="P6",
        success=success,
        duration_seconds=round(duration, 2),
        message=message,
        outputs=outputs,
    )


def _run_phase_p7(workspace: Path, state_manager: StateManager) -> PhaseResult:
    """P7: 증거 패키지 — evidence_chain.json 생성."""
    start = time.monotonic()
    outputs = []

    try:
        from scripts.run_provenance_builder import run_provenance_builder

        result = run_provenance_builder(workspace=str(workspace))
        outputs = result.get("outputs", [])

        evidence_chain = workspace / "10_evidence_pack" / "evidence_chain.json"
        success = evidence_chain.exists()
        message = "P7 완료: 증거 체인 생성" if success else "evidence_chain.json 미생성"

    except ImportError:
        evidence_chain = workspace / "10_evidence_pack" / "evidence_chain.json"
        success = evidence_chain.exists()
        message = "P7 완료 (run_provenance_builder.py 미설치)" if success else "증거 체인 미존재"
        if evidence_chain.exists():
            outputs.append(str(evidence_chain.relative_to(workspace)))

    duration = time.monotonic() - start
    return PhaseResult(
        phase="P7",
        success=success,
        duration_seconds=round(duration, 2),
        message=message,
        outputs=outputs,
    )


# Phase runner 매핑
PHASE_RUNNERS = {
    "P0": _run_phase_p0,
    "P0.5": _run_phase_p0_5,
    "P1": _run_phase_p1,
    "P1.5": _run_phase_p1_5,
    "P2": _run_phase_p2,
    "P3": _run_phase_p3,
    "P4": _run_phase_p4,
    "P5": _run_phase_p5,
    "P6": _run_phase_p6,
    "P7": _run_phase_p7,
}


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Engine
# ─────────────────────────────────────────────────────────────────────────────


class PipelineEngine:
    """
    P0→P7 파이프라인 실행 엔진.

    Responsibilities:
    - Phase 순차 실행
    - 게이트 조건 확인
    - 상태 추적 및 동기화
    - 섹션 병렬 실행 (P4)
    """

    def __init__(
        self,
        workspace: Path,
        skip_approvals: bool = False,
        parallel_sections: bool = True,
        start_phase: str = "P0",
        end_phase: str = "P7",
        section_ids: Optional[list[str]] = None,
    ):
        self.workspace = workspace
        self.skip_approvals = skip_approvals
        self.parallel_sections = parallel_sections
        self.start_phase = start_phase
        self.end_phase = end_phase
        self.section_ids = section_ids

        # StateManager 초기화
        self.state_manager = StateManager(workspace)

        # GateEvaluator 초기화
        self.gate_evaluator = GateEvaluator(
            workspace=workspace,
            orchestration_dir=PROJECT_ROOT / "orchestration",
        )

        # 결과 추적
        self.phases_completed: list[PhaseResult] = []
        self.phases_blocked: list[PhaseResult] = []
        self.phases_executed: list[str] = []

    def _check_gate(self, from_phase: str, to_phase: str) -> tuple[bool, str, str]:
        """
        게이트 조건을 확인한다.

        Returns:
            (can_proceed, result_status, gate_name)
            result_status: "passed" | "blocked" | "needs_human_approval"
        """
        gate_name = f"{from_phase}_to_{to_phase}"

        # auto gates (P0→P0.5, P0.5→P1, P1→P1.5, P3→P4, P4→P5, P6→P7) use evaluate_auto_gate
        # human gates (P2→P3, P5_to_P6, P1.5_to_P2) use evaluate() directly
        if gate_name in ("P2_to_P3", "P5_to_P6", "P1.5_to_P2"):
            result = self.gate_evaluator.evaluate(gate_name)
        else:
            result = self.gate_evaluator.evaluate_auto_gate(from_phase, to_phase)

        if result["result"] == "passed":
            return True, "passed", gate_name
        elif result["result"] == "needs_human_approval":
            if self.skip_approvals:
                # 테스트 모드: 강제 진행 + 게이트 기록
                self._record_skip_approval(gate_name)
                return True, "passed", gate_name
            return False, "needs_human_approval", gate_name
        elif result["result"] == "blocked":
            if result.get("can_override", False) and self.skip_approvals:
                # 테스트 모드: 강제 진행 + 게이트 기록
                self._record_skip_approval(gate_name)
                return True, "passed", gate_name
            return False, "blocked", gate_name
        else:
            # 알 수 없는 결과 → 자동 통과
            return True, "passed", gate_name

    def _record_skip_approval(self, gate_name: str) -> None:
        """
        skip-approval 모드에서 human gate를 바이패스할 때 approval_gates.json에 기록한다.

        이렇게 하면 determine_phase()가 게이트를 approved로 인식하여
        current_phase가 올바르게 계산된다.
        """
        import json

        approval_gates_path = self.workspace / "approval_gates.json"
        if approval_gates_path.exists():
            approval_data = json.loads(approval_gates_path.read_text(encoding="utf-8"))
        else:
            approval_data = {"gates": {}, "project_id": self.workspace.name}

        decided_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        gate_config = self.gate_evaluator._get_gate_config(gate_name) or {}
        required_approvers = gate_config.get("required_approvers", ["project_manager", "consultant_lead"])

        approval_data.setdefault("gates", {})[gate_name] = {
            "gate_name": gate_name,
            "approval_type": "human",
            "required_approvers": required_approvers,
            "current_approvers": [
                {
                    "approver": "automation",
                    "signature": "skip-approval",
                    "decided_at": decided_at,
                    "notes": "Automated approval via --skip-approval flag",
                }
            ],
            "status": "approved",
            "decision": "approved",
            "decided_at": decided_at,
            "decided_by": "automation",
            "requested_at": approval_data.get("gates", {}).get(gate_name, {}).get("requested_at", decided_at),
            "requested_by": "run_pipeline",
        }
        approval_gates_path.write_text(
            json.dumps(approval_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        # Keep state_manager's in-memory _approval_gates in sync so that
        # the caller's sync() call does not overwrite our direct write.
        self.state_manager._approval_gates = approval_data

    def _wait_for_approval(self, gate_name: str) -> bool:
        """사용자 게이트 승인을 기다린다."""
        from scripts.wait_for_approval import wait_for_approval

        gate_config = self.gate_evaluator._get_gate_config(gate_name) or {}
        required_approvers = gate_config.get("required_approvers", ["project_manager", "consultant_lead"])

        result = wait_for_approval(
            workspace=str(self.workspace),
            gate_name=gate_name,
            required_approvers=required_approvers,
            state_manager=self.state_manager,
        )
        return result.decision == "approved"

    def run(self) -> PipelineResult:
        """파이프라인을 실행하고 결과를 반환한다."""
        overall_start = time.monotonic()

        # context_bus.ensure
        ensure_context_bus(self.workspace)

        # Phase 인덱스 범위 계산 (루프 진입 전에 한 번)
        start_idx = PHASE_ORDER.index(self.start_phase)
        end_idx = PHASE_ORDER.index(self.end_phase)

        # Phase 순회
        for i, phase in enumerate(PHASE_ORDER):
            # 시작/종료 필터 (인덱스 기반)
            if i < start_idx:
                continue
            if i > end_idx:
                break

            next_phase = NEXT_PHASE.get(phase)

            # Mid-pipeline entry: verify entry conditions before running
            # (prevents --start P3 from bypassing P2 approval gate)
            if phase == self.start_phase:
                entry_ok, failed = self.gate_evaluator._check_entry_conditions(phase)
                if not entry_ok:
                    # In skip-approval mode, record the gate bypass and proceed
                    if self.skip_approvals:
                        for f in failed:
                            if f.startswith("entry_gate_not_approved:"):
                                gate_name = f.split(":", 1)[1]
                                self._record_skip_approval(gate_name)
                    else:
                        self.gate_evaluator._register_blocking_issues(phase, failed)
                        self.state_manager.sync()
                        duration = time.monotonic() - overall_start
                        failed_desc = "; ".join(failed)
                        return PipelineResult(
                            success=False,
                            phases_executed=self.phases_executed,
                            phases_completed=self.phases_completed,
                            phases_blocked=[],
                            total_duration_seconds=round(duration, 2),
                            blocked_at=phase,
                            error=f"Entry conditions not met for {phase}: {failed_desc}",
                        )

            runner = PHASE_RUNNERS.get(phase)
            if not runner:
                continue

            # runner 인자 분기
            if phase == "P0":
                phase_result = runner(self.workspace)
            elif phase == "P0.5":
                phase_result = runner(self.workspace)
            elif phase == "P1":
                phase_result = runner(self.workspace, self.state_manager)
            elif phase == "P1.5":
                phase_result = runner(self.workspace)
            elif phase == "P2":
                phase_result = runner(self.workspace, self.state_manager, self.skip_approvals)
            elif phase == "P3":
                phase_result = runner(self.workspace, self.state_manager)
            elif phase == "P4":
                phase_result = runner(
                    self.workspace,
                    self.state_manager,
                    parallel_sections=self.parallel_sections,
                    section_ids=self.section_ids,
                )
            elif phase == "P5":
                phase_result = runner(self.workspace, self.state_manager)
            elif phase in ("P6", "P7"):
                phase_result = runner(self.workspace, self.state_manager)
            else:
                continue

            # 결과 기록
            self.phases_executed.append(phase)
            if phase_result.success:
                self.phases_completed.append(phase_result)
                # Phase 완료 → 상태 갱신
                # Skip advancement when starting from a mid-pipeline phase:
                # the workspace may already be past this phase (e.g., P0/P1/P2
                # completed via separate CLI calls before run-pipeline).
                if phase == self.start_phase and self.state_manager.get_current_phase() != phase:
                    pass  # already past this phase — do not re-advance
                elif next_phase:
                    # Avoid double-advance: if the phase runner already called
                    # set_phase_status(phase, "complete") (which advances current_phase),
                    # current_phase will already be next_phase.
                    if self.state_manager.get_current_phase() != next_phase:
                        self.state_manager.advance_phase(phase, next_phase)
                else:
                    self.state_manager.set_phase_status(phase, "complete")
                self.state_manager.sync()

                # Phase 실행 후 게이트 확인 (첫 번째 phase 제외)
                # start_phase는 이전 phase 없이 시작하므로 gate check 불필요
                if next_phase is not None and phase != self.start_phase:
                    can_proceed, gate_status, gate_name = self._check_gate(phase, next_phase)

                    if not can_proceed:
                        if gate_status == "needs_human_approval":
                            # 승인 대기
                            approved = self._wait_for_approval(gate_name)
                            if not approved:
                                duration = time.monotonic() - overall_start
                                return PipelineResult(
                                    success=False,
                                    phases_executed=self.phases_executed,
                                    phases_completed=self.phases_completed,
                                    phases_blocked=self.phases_blocked,
                                    total_duration_seconds=round(duration, 2),
                                    blocked_at=phase,
                                    error=f"Gate '{gate_name}' approval rejected",
                                )
                        else:
                            # blocked
                            duration = time.monotonic() - overall_start
                            return PipelineResult(
                                success=False,
                                phases_executed=self.phases_executed,
                                phases_completed=self.phases_completed,
                                phases_blocked=self.phases_blocked,
                                total_duration_seconds=round(duration, 2),
                                blocked_at=phase,
                                error=f"Gate '{gate_name}' blocked: {gate_status}",
                            )
            else:
                self.phases_blocked.append(phase_result)
                # 실패 시 blocking issue 추가
                self.state_manager.add_blocking_issue(
                    issue={
                        "reason": phase_result.message,
                        "severity": "blocker",
                        "phase": phase,
                    },
                    phase=phase,
                )
                self.state_manager.sync()
                duration = time.monotonic() - overall_start
                return PipelineResult(
                    success=False,
                    phases_executed=self.phases_executed,
                    phases_completed=self.phases_completed,
                    phases_blocked=self.phases_blocked,
                    total_duration_seconds=round(duration, 2),
                    blocked_at=phase,
                    error=phase_result.message,
                )

        duration = time.monotonic() - overall_start
        return PipelineResult(
            success=True,
            phases_executed=self.phases_executed,
            phases_completed=self.phases_completed,
            phases_blocked=[],
            total_duration_seconds=round(duration, 2),
        )

    def print_summary(self, result: PipelineResult) -> None:
        """파이프라인 실행 결과를 요약 출력한다."""
        print(f"\n{'=' * 60}")
        print(f" Pipeline Run Summary")
        print(f"{'=' * 60}")
        print(f" Workspace : {self.workspace}")
        print(f" Started   : {self.start_phase} → {self.end_phase}")
        print(f" Duration  : {result.total_duration_seconds}s")
        print()

        if result.phases_completed:
            print(" Completed Phases:")
            for pr in result.phases_completed:
                print(f"  ✅ {pr.phase} | {pr.duration_seconds}s | {pr.message}")
                if pr.outputs:
                    for out in pr.outputs[:3]:
                        print(f"     └── {out}")
                    if len(pr.outputs) > 3:
                        print(f"     ... +{len(pr.outputs) - 3} more")

        if result.phases_blocked:
            print("\n Blocked Phases:")
            for pr in result.phases_blocked:
                print(f"  ⛔ {pr.phase} | {pr.error}")

        if result.blocked_at:
            print(f"\n Stopped at: {result.blocked_at}")

        print(f"\n Overall: {'✅ SUCCESS' if result.success else '❌ FAILED'}")
        print(f"{'=' * 60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI 진입점
# ─────────────────────────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--workspace",
    "-w",
    "workspace",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="워크스페이스 경로: /path/to/PRJ-YYYY-CODE-NNN",
)
@click.option(
    "--start-phase",
    "-s",
    "start_phase",
    type=click.Choice(PHASE_ORDER),
    default="P0",
    help="시작 Phase (default: P0)",
)
@click.option(
    "--end-phase",
    "-e",
    "end_phase",
    type=click.Choice(PHASE_ORDER),
    default="P7",
    help="종료 Phase (default: P7)",
)
@click.option(
    "--skip-approvals",
    is_flag=True,
    default=False,
    help="테스트 모드: 게이트 승인을 건너뜀",
)
@click.option(
    "--no-parallel",
    is_flag=True,
    default=False,
    help="섹션 병렬 실행 비활성화",
)
@click.option(
    "--section",
    "-S",
    "section_ids",
    multiple=True,
    help="P4에서 실행할 섹션 ID (여러 개 지정 가능, 예: --section SEC-3.1 --section SEC-3.2)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="실행 없이 게이트 상태만 확인",
)
def main(
    workspace: Path,
    start_phase: str,
    end_phase: str,
    skip_approvals: bool,
    no_parallel: bool,
    section_ids: tuple[str, ...],
    dry_run: bool,
) -> int:
    """P0→P7 ESG 보고서 생성 파이프라인 실행."""
    print(f"=== Pipeline Run ===")
    print(f"Workspace : {workspace}")
    print(f"Range    : {start_phase} → {end_phase}")
    print(f"Mode     : {'TEST (skip approvals)' if skip_approvals else 'NORMAL'}")
    print(f"Sections : {'all' if not section_ids else ', '.join(section_ids)}")
    print()

    # Dry-run: 게이트 상태만 확인
    if dry_run:
        gate_eval = GateEvaluator(
            workspace=workspace,
            orchestration_dir=PROJECT_ROOT / "orchestration",
        )
        print("Gate Status Check:")
        for phase in PHASE_ORDER:
            next_phase = NEXT_PHASE.get(phase)
            if next_phase is None:
                continue
            gate_name = f"{phase}_to_{next_phase}"
            # auto gates use evaluate_auto_gate, human gates use evaluate()
            if gate_name in ("P2_to_P3", "P5_to_P6", "P1.5_to_P2"):
                result = gate_eval.evaluate(gate_name)
            else:
                result = gate_eval.evaluate_auto_gate(phase, next_phase)
            print(f"  {gate_name}: {result['result']}")
        return 0

    # 파이프라인 실행
    engine = PipelineEngine(
        workspace=workspace,
        skip_approvals=skip_approvals,
        parallel_sections=not no_parallel,
        start_phase=start_phase,
        end_phase=end_phase,
        section_ids=list(section_ids) if section_ids else None,
    )

    result = None
    try:
        result = engine.run()
        engine.print_summary(result)
        return 0 if result.success else 1
    except Exception as e:
        print(f"\n❌ Pipeline error: {e}", file=sys.stderr)
        return 1
    finally:
        # HD-4: 성공/실패 무관하게 sync_workspace() 호출
        if result is not None:
            try:
                from scripts.utils import sync_workspace

                sync_result = sync_workspace(workspace)
                print(
                    f"[sync_workspace] Done — "
                    f"{sync_result.get('blocking_issues', 0)} issues, "
                    f"{sync_result.get('next_actions', 0)} actions, "
                    f"project_state={'OK' if sync_result.get('project_state') else 'FAILED'}"
                )
            except Exception as sync_err:
                print(f"[sync_workspace] Warning: sync failed: {sync_err}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
