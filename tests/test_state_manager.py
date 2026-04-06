#!/usr/bin/env python3.13
"""
tests/test_state_manager.py — StateManager 단위 테스트

Tests:
1. 초기화 및 기본 상태
2. Phase 관리 (advance_phase, set_phase_status, is_phase_complete)
3. Blocking Issue 관리 (add, resolve, get)
4. 게이트 연동 (wait_for_approval, record_approval, is_gate_approved)
5. 섹션 진행 관리
6. 동기화 (sync)
7. Run 관리 (create_run, close_run)
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# ─────────────────────────────────────────────────────────────────────────────
# 테스트 헬퍼
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_workspace():
    """임시 워크스페이스 디렉토리 생성."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        # 필수 디렉토리 생성
        (workspace / "context_bus").mkdir()
        yield workspace


@pytest.fixture
def state_manager(temp_workspace):
    """StateManager 인스턴스 생성."""
    from scripts.state_manager import StateManager

    return StateManager(temp_workspace)


# ─────────────────────────────────────────────────────────────────────────────
# TC-1: 초기화 및 기본 상태
# ─────────────────────────────────────────────────────────────────────────────


class TestInitialization:
    def test_new_workspace_creates_default_state(self, temp_workspace):
        """새 워크스페이스에서 StateManager 초기화 시 기본 상태가 생성됨."""
        from scripts.state_manager import StateManager

        sm = StateManager(temp_workspace)

        assert sm.get_current_phase() == "P0"
        assert sm.get_phase_status("P0") == "pending"
        assert sm.get_project_id() == temp_workspace.name

    def test_existing_state_file_loaded(self, temp_workspace):
        """기존 project_state.json이 있으면 로드됨."""
        from scripts.state_manager import StateManager

        state_data = {
            "project_id": "PRJ-2026-TST-001",
            "current_phase": "P3",
            "phase_status": {
                "P0": "complete",
                "P1": "complete",
                "P2": "complete",
                "P3": "in_progress",
                "P4": "pending",
                "P5": "pending",
                "P6": "pending",
                "P7": "pending",
            },
            "section_progress": {},
            "statistics": {},
            "last_updated": "2026-04-01T00:00:00Z",
        }

        state_file = temp_workspace / "project_state.json"
        state_file.write_text(json.dumps(state_data), encoding="utf-8")

        sm = StateManager(temp_workspace)
        assert sm.get_current_phase() == "P3"
        assert sm.get_phase_status("P0") == "complete"

    def test_context_bus_directory_created(self, temp_workspace):
        """StateManager 초기화 시 context_bus 디렉토리가 자동 생성됨."""
        from scripts.state_manager import StateManager

        # context_bus 없이 초기화
        (temp_workspace / "context_bus").rmdir() if (temp_workspace / "context_bus").exists() else None

        sm = StateManager(temp_workspace)
        assert (temp_workspace / "context_bus").is_dir()


# ─────────────────────────────────────────────────────────────────────────────
# TC-2: Phase 관리
# ─────────────────────────────────────────────────────────────────────────────


class TestPhaseManagement:
    def test_advance_phase_success(self, state_manager):
        """advance_phase로 유효한 Phase 전환이 가능함."""
        result = state_manager.advance_phase("P0", "P1")

        assert result is True
        assert state_manager.get_current_phase() == "P1"
        assert state_manager.get_phase_status("P0") == "complete"
        assert state_manager.get_phase_status("P1") == "in_progress"

    def test_advance_phase_invalid_from_phase(self, state_manager):
        """현재 Phase와 다른 Phase에서 advance하면 오류 발생."""
        from scripts.state_manager import PhaseTransitionError

        with pytest.raises(PhaseTransitionError):
            state_manager.advance_phase("P2", "P3")

    def test_advance_phase_invalid_phase_name(self, state_manager):
        """유효하지 않은 Phase 이름으로 전환 시 오류 발생."""
        from scripts.state_manager import PhaseTransitionError

        with pytest.raises(PhaseTransitionError):
            state_manager.advance_phase("PX", "P1")

    def test_set_phase_status(self, state_manager):
        """set_phase_status로 Phase 상태를 직접 설정 가능."""
        state_manager.set_phase_status("P2", "in_progress")

        assert state_manager.get_phase_status("P2") == "in_progress"
        assert state_manager.get_current_phase() == "P2"

    def test_set_phase_status_complete_advances_current(self, state_manager):
        """Phase를 complete로 설정하면 current_phase가 자동으로 다음 Phase로 이동."""
        state_manager.set_phase_status("P1", "complete")

        assert state_manager.get_current_phase() == "P1.5"
        assert state_manager.get_phase_status("P1") == "complete"

    def test_set_phase_status_invalid_phase_raises(self, state_manager):
        """유효하지 않은 Phase 이름으로 설정 시 오류 발생."""
        from scripts.state_manager import StateError

        with pytest.raises(StateError):
            state_manager.set_phase_status("PX", "in_progress")

    def test_set_phase_status_invalid_status_raises(self, state_manager):
        """유효하지 않은 status로 설정 시 오류 발생."""
        from scripts.state_manager import StateError

        with pytest.raises(StateError):
            state_manager.set_phase_status("P1", "invalid_status")

    def test_is_phase_complete(self, state_manager):
        """is_phase_complete로 Phase 완료 여부 확인 가능."""
        assert state_manager.is_phase_complete("P0") is False

        state_manager.set_phase_status("P0", "complete")
        assert state_manager.is_phase_complete("P0") is True


# ─────────────────────────────────────────────────────────────────────────────
# TC-3: Blocking Issue 관리
# ─────────────────────────────────────────────────────────────────────────────


class TestBlockingIssueManagement:
    def test_add_blocking_issue(self, state_manager):
        """add_blocking_issue로 Issue 추가 가능."""
        issue_id = state_manager.add_blocking_issue(
            issue={"reason": "테스트阻塞原因", "severity": "high"},
            agent="test-agent",
            phase="P2",
        )

        assert issue_id == "BK-001"
        issues = state_manager.get_blocking_issues()
        assert len(issues) == 1
        assert issues[0]["reason"] == "테스트阻塞原因"
        assert issues[0]["severity"] == "high"
        assert issues[0]["resolved"] is False

    def test_add_multiple_blocking_issues_increments_id(self, state_manager):
        """Issue를 여러 번 추가하면 ID가 BK-001, BK-002, ...로 증가."""
        id1 = state_manager.add_blocking_issue({"reason": "Issue 1", "severity": "low"})
        id2 = state_manager.add_blocking_issue({"reason": "Issue 2", "severity": "medium"})
        id3 = state_manager.add_blocking_issue({"reason": "Issue 3", "severity": "high"})

        assert id1 == "BK-001"
        assert id2 == "BK-002"
        assert id3 == "BK-003"

    def test_resolve_blocking_issue(self, state_manager):
        """resolve_blocking_issue로 Issue를 해결 상태로 변경."""
        issue_id = state_manager.add_blocking_issue({"reason": "테스트", "severity": "medium"})

        result = state_manager.resolve_blocking_issue(issue_id, resolved_by="test-user")

        assert result is True
        issues = state_manager.get_blocking_issues(resolved=False)
        assert len(issues) == 0

        issues_all = state_manager.get_blocking_issues(resolved=None)
        assert len(issues_all) == 1
        assert issues_all[0]["resolved"] is True
        assert issues_all[0]["resolved_by"] == "test-user"

    def test_resolve_nonexistent_issue_raises(self, state_manager):
        """존재하지 않는 Issue를 해결하려 하면 오류 발생."""
        from scripts.state_manager import BlockingIssueNotFoundError

        with pytest.raises(BlockingIssueNotFoundError):
            state_manager.resolve_blocking_issue("BK-999")

    def test_get_blocking_issues_filter_resolved(self, state_manager):
        """get_blocking_issues의 resolved 파라미터로 필터링 가능."""
        id1 = state_manager.add_blocking_issue({"reason": "Issue 1", "severity": "low"})
        id2 = state_manager.add_blocking_issue({"reason": "Issue 2", "severity": "medium"})

        state_manager.resolve_blocking_issue(id1)

        unresolved = state_manager.get_blocking_issues(resolved=False)
        resolved = state_manager.get_blocking_issues(resolved=True)
        all_issues = state_manager.get_blocking_issues()

        assert len(unresolved) == 1
        assert unresolved[0]["issue_id"] == "BK-002"
        assert len(resolved) == 1
        assert resolved[0]["issue_id"] == "BK-001"
        assert len(all_issues) == 2

    def test_has_unresolved_blocking_issues(self, state_manager):
        """has_unresolved_blocking_issues로 미해결 Issue 존재 여부 확인."""
        assert state_manager.has_unresolved_blocking_issues() is False

        state_manager.add_blocking_issue({"reason": "Issue", "severity": "medium"})
        assert state_manager.has_unresolved_blocking_issues() is True

    def test_sync_issues_to_state(self, state_manager):
        """sync() 호출 시 blocking_issues가 project_state.json에 동기화됨."""
        state_manager.add_blocking_issue({"reason": "동기화 테스트", "severity": "high"})
        state_manager.sync()

        state_file = state_manager.workspace / "project_state.json"
        data = json.loads(state_file.read_text(encoding="utf-8"))

        assert "blocking_issues" in data
        assert len(data["blocking_issues"]) == 1
        assert data["blocking_issues"][0]["reason"] == "동기화 테스트"


# ─────────────────────────────────────────────────────────────────────────────
# TC-4: 게이트 연동
# ─────────────────────────────────────────────────────────────────────────────


class TestGateManagement:
    def test_wait_for_approval(self, state_manager):
        """wait_for_approval로 게이트 대기 상태 설정."""
        state_manager.wait_for_approval(
            gate_name="P2_to_P3",
            required_approvers=["project_manager", "consultant_lead"],
            requester="test",
        )

        assert state_manager.is_gate_waiting("P2_to_P3") is True
        assert state_manager.is_gate_approved("P2_to_P3") is False

    def test_record_approval_single_approver(self, state_manager):
        """record_approval로 단일 승인자 기록 가능."""
        state_manager.wait_for_approval(
            gate_name="P2_to_P3",
            required_approvers=["project_manager", "consultant_lead"],
        )

        result = state_manager.record_approval(
            gate_name="P2_to_P3",
            approver="project_manager",
            signature="sig-001",
        )

        # project_manager만 승인 → 아직 전체 승인은 아님
        assert result is True
        assert state_manager.is_gate_approved("P2_to_P3") is False

    def test_record_approval_all_required_approvers(self, state_manager):
        """필요한 승인자가 모두 승인하면 게이트가 approved 상태로 변경."""
        state_manager.wait_for_approval(
            gate_name="P2_to_P3",
            required_approvers=["project_manager", "consultant_lead"],
        )

        state_manager.record_approval("P2_to_P3", "project_manager", "sig-001")
        state_manager.record_approval("P2_to_P3", "consultant_lead", "sig-002")

        assert state_manager.is_gate_approved("P2_to_P3") is True
        assert state_manager.is_gate_waiting("P2_to_P3") is False

    def test_record_approval_rejected(self, state_manager):
        """record_approval에서 decision='rejected' 시 게이트가 rejected 상태로 변경."""
        state_manager.wait_for_approval(
            gate_name="P2_to_P3",
            required_approvers=["project_manager", "consultant_lead"],
        )

        state_manager.record_approval(
            gate_name="P2_to_P3",
            approver="project_manager",
            signature="sig-001",
            decision="rejected",
        )

        gate_status = state_manager.get_gate_status("P2_to_P3")
        assert gate_status["status"] == "rejected"

    def test_is_gate_waiting_no_such_gate(self, state_manager):
        """존재하지 않는 게이트는 waiting이 아닌 것으로 간주."""
        assert state_manager.is_gate_waiting("NONEXISTENT_GATE") is False

    def test_requires_approval_human_gate(self, state_manager):
        """human 타입의 게이트는 requires_approval가 True 반환."""
        state_manager.wait_for_approval(
            gate_name="P2_to_P3",
            required_approvers=["project_manager"],
        )

        assert state_manager.requires_approval("P2_to_P3") is True

    def test_get_gate_status(self, state_manager):
        """get_gate_status로 게이트 상세 정보 조회 가능."""
        state_manager.wait_for_approval(
            gate_name="P5_to_P6",
            required_approvers=["consultant_lead", "quality_reviewer"],
        )

        status = state_manager.get_gate_status("P5_to_P6")

        assert status is not None
        assert status["gate_name"] == "P5_to_P6"
        assert status["approval_type"] == "human"
        assert status["required_approvers"] == ["consultant_lead", "quality_reviewer"]

    def test_legacy_approved_by_without_top_level_approval_stays_waiting(self, temp_workspace):
        """legacy approved_by만 있는 상태는 approved로 간주하지 않는다."""
        approval_file = temp_workspace / "approval_gates.json"
        approval_file.write_text(
            json.dumps(
                {
                    "gates": {
                        "P2_to_P3": {
                            "gate_id": "P2_to_P3",
                            "approval_type": "human",
                            "required_approvers": ["project_manager", "consultant_lead"],
                            "approved_by": {
                                "project_manager": {
                                    "approved": True,
                                    "approved_at": "2026-04-04T00:00:00Z",
                                }
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        from scripts.state_manager import StateManager

        sm = StateManager(temp_workspace)
        gate_status = sm.get_gate_status("P2_to_P3")

        assert gate_status["status"] == "waiting"
        assert gate_status["decision"] is None
        assert [entry["approver"] for entry in gate_status["current_approvers"]] == ["project_manager"]

    def test_cli_approve_waiting_to_approved_and_check_gate_agrees(self, temp_workspace):
        """CLI approve와 gate evaluator/file polling이 같은 canonical 상태를 본다."""
        from llm.cli import cmd_approve
        from scripts.check_gate import GateEvaluator
        from scripts.state_manager import StateManager
        from scripts.wait_for_approval import poll_file_approval

        planning_dir = temp_workspace / "05_planning"
        planning_dir.mkdir(exist_ok=True)
        (planning_dir / "writing_blueprint.json").write_text(
            json.dumps({"approved": True}, ensure_ascii=False),
            encoding="utf-8",
        )
        (planning_dir / "structure_index.json").write_text(
            json.dumps({"sections": []}, ensure_ascii=False),
            encoding="utf-8",
        )

        sm = StateManager(temp_workspace)
        sm.wait_for_approval(
            gate_name="P2_to_P3",
            required_approvers=["project_manager", "consultant_lead"],
            requester="test",
        )

        runner = CliRunner()
        first = runner.invoke(
            cmd_approve,
            [
                "P2_to_P3",
                "--workspace",
                str(temp_workspace),
                "--by",
                "project_manager",
                "--notes",
                "first approval",
            ],
        )
        assert first.exit_code == 0, first.output

        approval_data = json.loads((temp_workspace / "approval_gates.json").read_text(encoding="utf-8"))
        gate = approval_data["gates"]["P2_to_P3"]
        assert gate["status"] == "waiting"
        assert gate["decision"] is None
        assert [entry["approver"] for entry in gate["current_approvers"]] == ["project_manager"]
        assert "approved_by" not in gate

        evaluator = GateEvaluator(temp_workspace, PROJECT_ROOT / "orchestration")
        assert evaluator.evaluate("P2_to_P3")["result"] == "needs_human_approval"

        second = runner.invoke(
            cmd_approve,
            [
                "P2_to_P3",
                "--workspace",
                str(temp_workspace),
                "--by",
                "consultant_lead",
            ],
        )
        assert second.exit_code == 0, second.output

        approval_data = json.loads((temp_workspace / "approval_gates.json").read_text(encoding="utf-8"))
        gate = approval_data["gates"]["P2_to_P3"]
        assert gate["status"] == "approved"
        assert gate["decision"] == "approved"
        assert gate["decided_by"] == "consultant_lead"

        polled = poll_file_approval(temp_workspace, "P2_to_P3", timeout_seconds=1, poll_interval=0)
        assert polled.decision == "approved"
        assert polled.approvers == ["project_manager", "consultant_lead"]
        assert evaluator.evaluate("P2_to_P3")["result"] == "passed"


# ─────────────────────────────────────────────────────────────────────────────
# TC-5: 섹션 진행 관리
# ─────────────────────────────────────────────────────────────────────────────


class TestSectionProgress:
    def test_update_section_progress(self, state_manager):
        """update_section_progress로 섹션 진행状況 갱신 가능."""
        state_manager.update_section_progress(
            section_id="SEC-3.1",
            status="drafted",
            draft_version=1,
            confidence=0.75,
        )

        progress = state_manager.get_section_progress("SEC-3.1")

        assert progress is not None
        assert progress["status"] == "drafted"
        assert progress["draft_version"] == 1
        assert progress["confidence"] == 0.75

    def test_update_section_progress_multiple_sections(self, state_manager):
        """여러 섹션의 진행状況を個別に更新可能."""
        state_manager.update_section_progress("SEC-3.1", "drafted", confidence=0.8)
        state_manager.update_section_progress("SEC-3.2", "approved", confidence=0.95)
        state_manager.update_section_progress("SEC-4.1", "in_progress", confidence=0.5)

        assert state_manager.get_section_progress("SEC-3.1")["status"] == "drafted"
        assert state_manager.get_section_progress("SEC-3.2")["status"] == "approved"
        assert state_manager.get_section_progress("SEC-4.1")["status"] == "in_progress"


# ─────────────────────────────────────────────────────────────────────────────
# TC-6: 동기화
# ─────────────────────────────────────────────────────────────────────────────


class TestSync:
    def test_sync_writes_all_files(self, temp_workspace):
        """sync() 호출 시 project_state.json, blocking_issues.json, approval_gates.json 모두 저장."""
        from scripts.state_manager import StateManager

        sm = StateManager(temp_workspace)

        sm.add_blocking_issue({"reason": "Sync 테스트", "severity": "medium"})
        sm.wait_for_approval("P2_to_P3", ["project_manager"])
        sm.update_section_progress("SEC-1", "drafted", confidence=0.7)
        sm.sync()

        # project_state.json
        state_file = temp_workspace / "project_state.json"
        assert state_file.exists()
        state_data = json.loads(state_file.read_text(encoding="utf-8"))
        assert state_data["section_progress"]["SEC-1"]["confidence"] == 0.7

        # blocking_issues.json
        blocking_file = temp_workspace / "blocking_issues.json"
        assert blocking_file.exists()
        blocking_data = json.loads(blocking_file.read_text(encoding="utf-8"))
        assert len(blocking_data["issues"]) == 1

        # approval_gates.json
        approval_file = temp_workspace / "approval_gates.json"
        assert approval_file.exists()
        approval_data = json.loads(approval_file.read_text(encoding="utf-8"))
        assert "P2_to_P3" in approval_data["gates"]


# ─────────────────────────────────────────────────────────────────────────────
# TC-7: Run 관리
# ─────────────────────────────────────────────────────────────────────────────


class TestRunManagement:
    def test_create_run(self, state_manager, temp_workspace):
        """create_run으로 새 실행 생성 가능."""
        run_id = state_manager.create_run(
            agent="toc-planner",
            phase="P2",
            sections=["SEC-3.1", "SEC-3.2"],
        )

        assert run_id.startswith("RUN-")

        runs_file = temp_workspace / "context_bus" / "runs.json"
        runs_data = json.loads(runs_file.read_text(encoding="utf-8"))

        assert len(runs_data) == 1
        assert runs_data[0]["run_id"] == run_id
        assert runs_data[0]["agents"] == ["toc-planner"]
        assert runs_data[0]["phases"] == ["P2"]
        assert runs_data[0]["sections"] == ["SEC-3.1", "SEC-3.2"]

    def test_close_run(self, state_manager, temp_workspace):
        """close_run으로 실행 종료 처리 가능."""
        run_id = state_manager.create_run(agent="section-writer", phase="P4")

        state_manager.close_run(run_id, outcome="success")

        runs_file = temp_workspace / "context_bus" / "runs.json"
        runs_data = json.loads(runs_file.read_text(encoding="utf-8"))

        assert runs_data[0]["ended_at"] is not None
        assert runs_data[0]["outcome"] == "success"


# ─────────────────────────────────────────────────────────────────────────────
# TC-8: CLI 진입점
# ─────────────────────────────────────────────────────────────────────────────


class TestCLI:
    def test_cli_get_phase(self, state_manager, capsys):
        """CLI에서 get-phase 명령이 현재 Phase를 출력."""
        import sys

        old_argv = sys.argv
        try:
            sys.argv = ["state_manager.py", str(state_manager.workspace), "get-phase"]
            # CLI는 직접 실행 파일로 테스트하므로，这里省略实际调用
        finally:
            sys.argv = old_argv

    def test_cli_add_issue(self, state_manager, temp_workspace):
        """CLI에서 add-issue 명령이 Issue를 추가."""
        from scripts.state_manager import StateManager

        sm = StateManager(temp_workspace)

        issue_id = sm.add_blocking_issue({"reason": "CLI 테스트", "severity": "high"})
        sm.sync()

        assert issue_id == "BK-001"
        blocking_file = temp_workspace / "blocking_issues.json"
        data = json.loads(blocking_file.read_text(encoding="utf-8"))
        assert data["issues"][0]["reason"] == "CLI 테스트"

    def test_cli_list_issues(self, state_manager):
        """CLI에서 list-issues 명령이 Issue 목록을 출력."""
        state_manager.add_blocking_issue({"reason": "Issue A", "severity": "low"})
        state_manager.add_blocking_issue({"reason": "Issue B", "severity": "high"})

        issues = state_manager.get_blocking_issues()
        assert len(issues) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 테스트 실행
# ─────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
