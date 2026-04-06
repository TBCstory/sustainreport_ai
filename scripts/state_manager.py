#!/usr/bin/env python3.13
"""
state_manager.py — 프로젝트별 Phase 상태 추적, 전환 로직, Blocking Issue 관리

역할:
1. Phase 관리 — 현재 Phase 추적, 전환, 완료 상태
2. Blocking Issue 관리 — 추가/해결/조회
3. 게이트 연동 — 승인 대기/기록
4. 상태 파일 동기화 — project_state.json, blocking_issues.json, approval_gates.json

사용법:
    from scripts.state_manager import StateManager
    sm = StateManager("/path/to/PRJ-YYYY-CODE-NNN")
    current = sm.get_current_phase()
    sm.advance_phase("P1", "P2")
    issue_id = sm.add_blocking_issue({"reason": "파일이 누락됨", "severity": "blocker"})
    sm.sync()
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from scripts.utils import generate_run_id

# ─────────────────────────────────────────────────────────────────────────────
# 경로 상수
# ─────────────────────────────────────────────────────────────────────────────

STATE_FILE = "project_state.json"
BLOCKING_FILE = "blocking_issues.json"
APPROVAL_FILE = "approval_gates.json"
APPROVAL_STATUSES = {"waiting", "approved", "rejected"}

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


def _default_approval_gates(project_id: str | None = None) -> dict:
    """기본 approval_gates.json shape를 반환한다."""
    data = {"gates": {}}
    if project_id:
        data["project_id"] = project_id
    return data


def _dedupe_current_approvers(entries: list[dict]) -> list[dict]:
    """approver 기준으로 current_approvers를 정규화한다."""
    deduped: list[dict] = []
    index_by_approver: dict[str, int] = {}

    for entry in entries:
        approver = entry.get("approver")
        if not approver:
            continue

        normalized = {
            "approver": approver,
            "signature": entry.get("signature"),
            "decided_at": entry.get("decided_at"),
        }
        if entry.get("notes"):
            normalized["notes"] = entry["notes"]

        existing_index = index_by_approver.get(approver)
        if existing_index is None:
            index_by_approver[approver] = len(deduped)
            deduped.append(normalized)
        else:
            deduped[existing_index] = {
                **deduped[existing_index],
                **{k: v for k, v in normalized.items() if v is not None},
            }

    return deduped


def _legacy_current_approvers(gate_entry: dict) -> list[dict]:
    """legacy approved_by dict를 current_approvers list로 변환한다."""
    approved_by = gate_entry.get("approved_by")
    if not isinstance(approved_by, dict):
        return []

    current_approvers: list[dict] = []
    for approver, meta in approved_by.items():
        if isinstance(meta, dict) and meta.get("approved") is False:
            continue

        meta = meta if isinstance(meta, dict) else {}
        entry = {
            "approver": approver,
            "signature": meta.get("signature"),
            "decided_at": meta.get("decided_at") or meta.get("approved_at"),
        }
        if meta.get("notes"):
            entry["notes"] = meta["notes"]
        current_approvers.append(entry)

    return current_approvers


def _infer_legacy_decided_by(gate_entry: dict) -> str | None:
    """legacy approved_by에서 마지막 승인자를 추정한다."""
    approved_by = gate_entry.get("approved_by")
    if not isinstance(approved_by, dict) or not approved_by:
        return None
    return next(reversed(approved_by))


def normalize_gate_entry(gate_name: str, gate_entry: dict | None) -> dict:
    """approval gate entry를 canonical shape로 정규화한다."""
    source = dict(gate_entry or {})
    current_approvers = source.get("current_approvers")
    if not isinstance(current_approvers, list):
        current_approvers = []

    current_approvers = _dedupe_current_approvers(current_approvers + _legacy_current_approvers(source))

    status = source.get("status")
    if status not in APPROVAL_STATUSES:
        if source.get("approved") is True:
            status = "approved"
        elif source.get("decision") == "rejected":
            status = "rejected"
        else:
            status = "waiting"

    decision = source.get("decision")
    if decision not in {"approved", "rejected"}:
        if status == "approved":
            decision = "approved"
        elif status == "rejected":
            decision = "rejected"
        else:
            decision = None

    decided_by = source.get("decided_by")
    if not decided_by and status == "approved":
        decided_by = _infer_legacy_decided_by(source)

    normalized = {
        "gate_name": source.get("gate_name") or source.get("gate_id") or gate_name,
        "approval_type": source.get("approval_type", "human"),
        "required_approvers": list(source.get("required_approvers", []) or []),
        "current_approvers": current_approvers,
        "status": status,
        "requested_at": source.get("requested_at") or source.get("created_at") or source.get("approved_at"),
        "decided_at": source.get("decided_at") or source.get("approved_at"),
        "decided_by": decided_by,
        "decision": decision,
    }

    for extra_key in ("requested_by", "override", "override_reason"):
        if extra_key in source:
            normalized[extra_key] = source[extra_key]

    return normalized


def normalize_approval_gates_data(data: dict | None, project_id: str | None = None) -> dict:
    """approval_gates.json payload 전체를 canonical shape로 정규화한다."""
    source = data if isinstance(data, dict) else {}
    normalized = _default_approval_gates(project_id=project_id)

    for key in ("project_id", "current_phase", "created_at", "updated_at"):
        if key in source:
            normalized[key] = source[key]

    if project_id and "project_id" not in normalized:
        normalized["project_id"] = project_id

    gates = source.get("gates")
    if not isinstance(gates, dict):
        return normalized

    normalized["gates"] = {
        gate_name: normalize_gate_entry(gate_name, gate_entry) for gate_name, gate_entry in gates.items()
    }
    return normalized


# ─────────────────────────────────────────────────────────────────────────────
# 예외
# ─────────────────────────────────────────────────────────────────────────────


class StateError(Exception):
    """상태 관리 일반 오류."""

    pass


class PhaseTransitionError(StateError):
    """유효하지 않은 Phase 전환 시도."""

    pass


class BlockingIssueNotFoundError(StateError):
    """지정한 Blocking Issue를 찾을 수 없음."""

    pass


# ─────────────────────────────────────────────────────────────────────────────
# StateManager
# ─────────────────────────────────────────────────────────────────────────────


class StateManager:
    """
    프로젝트 워크스페이스의 Phase 상태, Blocking Issue, 게이트 승인을 관리한다.

    모든 상태 변경은 메모리에서 즉시 반영되며, sync() 호출 시 파일에 기록된다.
    """

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace)
        self._ensure_directories()

        # 메모리 내 상태 캐시
        self._state: dict = self._load_state()
        self._blocking_issues: list[dict] = self._load_blocking_issues()
        self._approval_gates: dict = self._load_approval_gates()

    # ─────────────────────────────────────────────────────────────────────────
    # 내부 헬퍼
    # ─────────────────────────────────────────────────────────────────────────

    def _ensure_directories(self) -> None:
        """워크스페이스 기본 디렉토리 생성."""
        (self.workspace / "context_bus").mkdir(parents=True, exist_ok=True)
        (self.workspace / "05_planning").mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> dict:
        """project_state.json 로드."""
        path = self.workspace / STATE_FILE
        if not path.exists():
            return self._default_state()
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return self._default_state()

    def _load_blocking_issues(self) -> list[dict]:
        """blocking_issues.json 로드."""
        path = self.workspace / BLOCKING_FILE
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("issues", [])
        except (json.JSONDecodeError, OSError):
            return []

    def _load_approval_gates(self) -> dict:
        """approval_gates.json 로드."""
        path = self.workspace / APPROVAL_FILE
        if not path.exists():
            return _default_approval_gates(project_id=self.workspace.name)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return normalize_approval_gates_data(data, project_id=self.workspace.name)
        except (json.JSONDecodeError, OSError):
            return _default_approval_gates(project_id=self.workspace.name)

    def _default_state(self) -> dict:
        """기본 project_state.json 상태."""
        return {
            "project_id": self.workspace.name,
            "current_phase": "P0",
            "phase_status": {phase: "pending" for phase in PHASE_ORDER},
            "section_progress": {},
            "statistics": {
                "total_segments": 0,
                "segments_processed": 0,
                "total_sections": 0,
                "sections_drafted": 0,
                "sections_approved": 0,
                "draft_confidence_avg": 0.0,
            },
            "last_updated": utc_now(),
            "updated_by": "state_manager",
        }

    def _persist_state(self) -> None:
        """project_state.json 저장."""
        self._state["last_updated"] = utc_now()
        path = self.workspace / STATE_FILE
        path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _persist_blocking_issues(self) -> None:
        """blocking_issues.json 저장."""
        path = self.workspace / BLOCKING_FILE
        data = {"issues": self._blocking_issues}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _persist_approval_gates(self) -> None:
        """approval_gates.json 저장."""
        path = self.workspace / APPROVAL_FILE
        self._approval_gates = normalize_approval_gates_data(self._approval_gates, project_id=self.workspace.name)
        if "created_at" not in self._approval_gates:
            self._approval_gates["created_at"] = utc_now()
        self._approval_gates["updated_at"] = utc_now()
        path.write_text(json.dumps(self._approval_gates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _next_issue_id(self) -> str:
        """다음 Blocking Issue ID 생성."""
        if not self._blocking_issues:
            return "BK-001"
        max_num = 0
        for issue in self._blocking_issues:
            try:
                num = int(issue.get("issue_id", "BK-000").replace("BK-", ""), 10)
                if num > max_num:
                    max_num = num
            except ValueError:
                continue
        return f"BK-{max_num + 1:03d}"

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 관리
    # ─────────────────────────────────────────────────────────────────────────

    def get_current_phase(self) -> str:
        """현재 Phase 반환."""
        return self._state.get("current_phase", "P0")

    def get_phase_status(self, phase: str) -> str:
        """특정 Phase 상태 반환 (pending/in_progress/complete)."""
        return self._state.get("phase_status", {}).get(phase, "pending")

    def is_phase_complete(self, phase: str) -> bool:
        """해당 Phase가 완료되었는지 반환."""
        return self.get_phase_status(phase) == "complete"

    def advance_phase(self, from_phase: str, to_phase: str) -> bool:
        """
        Phase를 from_phase에서 to_phase로 전환한다.

        Args:
            from_phase: 현재 Phase
            to_phase: 다음 Phase

        Returns:
            True: 전환 성공

        Raises:
            PhaseTransitionError: 유효하지 않은 전환 시도
        """
        if from_phase not in PHASE_ORDER or to_phase not in PHASE_ORDER:
            raise PhaseTransitionError(f"Invalid phase: {from_phase} -> {to_phase}")

        current = self.get_current_phase()
        if current != from_phase:
            raise PhaseTransitionError(f"Cannot advance from {from_phase}: current phase is {current}")

        # Phase 상태 갱신
        phase_status = self._state.get("phase_status", {})
        phase_status[from_phase] = "complete"
        if to_phase is not None:
            phase_status[to_phase] = "in_progress"
        self._state["phase_status"] = phase_status
        self._state["current_phase"] = to_phase if to_phase else self._state.get("current_phase", to_phase)

        self._persist_state()
        return True

    def set_phase_status(self, phase: str, status: str) -> None:
        """
        Phase 상태를 직접 설정 (in_progress, pending, complete).

        Raises:
            StateError: 알 수 없는 phase 또는 status
        """
        if phase not in PHASE_ORDER:
            raise StateError(f"Unknown phase: {phase}")
        valid_statuses = {"pending", "in_progress", "complete"}
        if status not in valid_statuses:
            raise StateError(f"Invalid status '{status}': must be one of {valid_statuses}")

        phase_status = self._state.get("phase_status", {})
        phase_status[phase] = status
        self._state["phase_status"] = phase_status

        # current_phase 갱신
        if status == "complete":
            idx = PHASE_ORDER.index(phase)
            if idx < len(PHASE_ORDER) - 1:
                self._state["current_phase"] = PHASE_ORDER[idx + 1]
        elif status == "in_progress":
            self._state["current_phase"] = phase

        self._persist_state()

    def get_project_id(self) -> str:
        """프로젝트 ID 반환."""
        return self._state.get("project_id", self.workspace.name)

    # ─────────────────────────────────────────────────────────────────────────
    # Blocking Issue 관리
    # ─────────────────────────────────────────────────────────────────────────

    def add_blocking_issue(
        self,
        issue: dict,
        agent: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> str:
        """
        Blocking Issue를 추가하고 ID를 반환한다.

        Args:
            issue: {"reason": str, "severity": str, "section_id": str, ...}
            agent: 발생시킨 에이전트
            phase: 발생시킨 Phase

        Returns:
            issue_id (e.g., "BK-001")
        """
        issue_id = self._next_issue_id()
        new_issue: dict = {
            "issue_id": issue_id,
            "reason": issue.get("reason", "Unspecified"),
            "severity": issue.get("severity", "medium"),
            "section_id": issue.get("section_id"),
            "gate": issue.get("gate"),
            "resolved": False,
            "resolved_at": None,
            "resolved_by": None,
            "agent": agent,
            "phase": phase,
            "created_at": utc_now(),
        }
        self._blocking_issues.append(new_issue)
        self._persist_blocking_issues()
        self._sync_issues_to_state()
        return issue_id

    def resolve_blocking_issue(
        self,
        issue_id: str,
        resolved_by: Optional[str] = None,
    ) -> bool:
        """
        Blocking Issue를 해결됨으로 표시한다.

        Args:
            issue_id: "BK-001" 형식
            resolved_by: 해결자 이름

        Returns:
            True: 해결 성공

        Raises:
            BlockingIssueNotFoundError: 해당 Issue를 찾을 수 없음
        """
        for issue in self._blocking_issues:
            if issue.get("issue_id") == issue_id:
                issue["resolved"] = True
                issue["resolved_at"] = utc_now()
                issue["resolved_by"] = resolved_by
                self._persist_blocking_issues()
                self._sync_issues_to_state()
                return True
        raise BlockingIssueNotFoundError(f"Blocking issue not found: {issue_id}")

    def get_blocking_issues(
        self,
        resolved: Optional[bool] = None,
    ) -> list[dict]:
        """
        Blocking Issue 목록을 반환한다.

        Args:
            resolved: True=해결된 것만, False=미해결만, None=전체

        Returns:
            list[dict]: 필터링된 Blocking Issue 목록
        """
        if resolved is None:
            return list(self._blocking_issues)
        return [iss for iss in self._blocking_issues if iss.get("resolved") == resolved]

    def has_unresolved_blocking_issues(self) -> bool:
        """해결되지 않은 Blocking Issue가 있는지 반환."""
        return any(not iss.get("resolved", False) for iss in self._blocking_issues)

    def _sync_issues_to_state(self) -> None:
        """blocking_issues를 project_state.json에 동기화."""
        unresolved = self.get_blocking_issues(resolved=False)
        self._state["blocking_issues"] = [
            {
                "issue_id": iss["issue_id"],
                "reason": iss["reason"],
                "severity": iss["severity"],
                "section_id": iss.get("section_id"),
                "gate": iss.get("gate"),
                "created_at": iss["created_at"],
            }
            for iss in unresolved
        ]
        self._persist_state()

    # ─────────────────────────────────────────────────────────────────────────
    # 게이트 연동
    # ─────────────────────────────────────────────────────────────────────────

    def requires_approval(self, gate_name: str) -> bool:
        """
        해당 게이트가 사람 승인이 필요한지 반환.

        Args:
            gate_name: "P2_to_P3", "P5_to_P6" 등

        Returns:
            True: 사람 승인 필요
        """
        self._approval_gates = self._load_approval_gates()
        gate_data = self._approval_gates.get("gates", {}).get(gate_name)
        if not gate_data:
            return False  # 알 수 없는 게이트는 자동 처리
        return gate_data.get("approval_type") == "human"

    def get_gate_status(self, gate_name: str) -> dict | None:
        """게이트 상태 반환."""
        self._approval_gates = self._load_approval_gates()
        return self._approval_gates.get("gates", {}).get(gate_name)

    def wait_for_approval(
        self,
        gate_name: str,
        required_approvers: list[str],
        requester: str = "system",
    ) -> str:
        """
        게이트 승인 대기 상태로 설정한다.

        Args:
            gate_name: 게이트 ID
            required_approvers: 필요한 승인자 목록
            requester: 요청자

        Returns:
            gate_id
        """
        self._approval_gates = self._load_approval_gates()
        if "gates" not in self._approval_gates:
            self._approval_gates["gates"] = {}

        existing_gate = normalize_gate_entry(gate_name, self._approval_gates["gates"].get(gate_name))
        gate_entry = {
            **existing_gate,
            "gate_name": gate_name,
            "approval_type": existing_gate.get("approval_type", "human"),
            "required_approvers": list(required_approvers or existing_gate.get("required_approvers", [])),
            "current_approvers": (
                existing_gate.get("current_approvers", []) if existing_gate.get("status") == "waiting" else []
            ),
            "status": "waiting",
            "requested_at": utc_now(),
            "requested_by": requester,
            "decided_at": None,
            "decided_by": None,
            "decision": None,
        }
        self._approval_gates["gates"][gate_name] = gate_entry
        self._persist_approval_gates()
        return gate_name

    def record_approval(
        self,
        gate_name: str,
        approver: str,
        signature: str,
        decision: str = "approved",
        notes: Optional[str] = None,
    ) -> bool:
        """
        게이트 승인 또는 거부를 기록한다.

        Args:
            gate_name: 게이트 ID
            approver: 승인자 이름
            signature: 승인 서명 (임의 문자열)
            decision: "approved" 또는 "rejected"

        Returns:
            True: 기록 성공
        """
        self._approval_gates = self._load_approval_gates()
        gate = self._approval_gates.get("gates", {}).get(gate_name)
        if not gate:
            # 게이트가 없으면 자동 생성 후 기록
            self.wait_for_approval(gate_name, required_approvers=[approver])
            gate = self._approval_gates["gates"][gate_name]
        else:
            gate = normalize_gate_entry(gate_name, gate)
            self._approval_gates["gates"][gate_name] = gate

        if gate.get("status") in ("approved", "rejected"):
            # 이미 결정됨
            return False

        decided_at = utc_now()
        current_approvers = list(gate.get("current_approvers", []))
        updated = False
        for entry in current_approvers:
            if entry.get("approver") == approver:
                entry["signature"] = signature
                entry["decided_at"] = decided_at
                if notes:
                    entry["notes"] = notes
                updated = True
                break

        if not updated:
            new_entry = {
                "approver": approver,
                "signature": signature,
                "decided_at": decided_at,
            }
            if notes:
                new_entry["notes"] = notes
            current_approvers.append(new_entry)

        gate["current_approvers"] = _dedupe_current_approvers(current_approvers)

        # 필수 승인자 모두로부터 승인을 받았는지 확인
        required = set(gate.get("required_approvers", []))
        current = {a["approver"] for a in gate["current_approvers"]}
        all_approved = required.issubset(current) if required else decision == "approved"

        gate["status"] = "waiting"
        gate["decision"] = None
        gate["decided_at"] = None
        gate["decided_by"] = None

        if decision == "rejected":
            gate["status"] = "rejected"
            gate["decision"] = "rejected"
            gate["decided_at"] = decided_at
            gate["decided_by"] = approver
        elif all_approved:
            gate["status"] = "approved"
            gate["decision"] = "approved"
            gate["decided_at"] = decided_at
            gate["decided_by"] = approver

        self._persist_approval_gates()
        return True

    def is_gate_approved(self, gate_name: str) -> bool:
        """게이트가 승인되었는지 반환."""
        self._approval_gates = self._load_approval_gates()
        gate = self._approval_gates.get("gates", {}).get(gate_name)
        if not gate:
            return False
        return gate.get("status") == "approved"

    def is_gate_waiting(self, gate_name: str) -> bool:
        """게이트가 승인 대기 중인지 반환."""
        self._approval_gates = self._load_approval_gates()
        gate = self._approval_gates.get("gates", {}).get(gate_name)
        if not gate:
            return False
        return gate.get("status") == "waiting"

    # ─────────────────────────────────────────────────────────────────────────
    # 섹션 진행 관리
    # ─────────────────────────────────────────────────────────────────────────

    def update_section_progress(
        self,
        section_id: str,
        status: str,
        draft_version: Optional[int] = None,
        confidence: Optional[float] = None,
    ) -> None:
        """
        섹션 진행状況を更新する.

        Args:
            section_id: "SEC-3.1" 등
            status: "pending" | "in_progress" | "drafted" | "approved"
            draft_version: 초안 버전 번호
            confidence: 신뢰도 (0.0~1.0)
        """
        section_progress = self._state.get("section_progress", {})
        entry: dict = {"status": status}
        if draft_version is not None:
            entry["draft_version"] = draft_version
        if confidence is not None:
            entry["confidence"] = round(confidence, 2)
        section_progress[section_id] = entry
        self._state["section_progress"] = section_progress
        self._persist_state()

    def get_section_progress(self, section_id: str) -> dict | None:
        """섹션 진행状況 반환."""
        return self._state.get("section_progress", {}).get(section_id)

    # ─────────────────────────────────────────────────────────────────────────
    # 통계 업데이트
    # ─────────────────────────────────────────────────────────────────────────

    def update_statistics(self, stats: dict) -> None:
        """통계 정보를 갱신한다."""
        self._state["statistics"] = stats
        self._persist_state()

    # ─────────────────────────────────────────────────────────────────────────
    # 동기화
    # ─────────────────────────────────────────────────────────────────────────

    def sync(self) -> None:
        """
        메모리 내 상태를 모두 파일에 기록한다.

        project_state.json, blocking_issues.json, approval_gates.json 순서로 저장.
        """
        self._persist_state()
        self._persist_blocking_issues()
        self._persist_approval_gates()

    # ─────────────────────────────────────────────────────────────────────────
    # Run ID 관리
    # ─────────────────────────────────────────────────────────────────────────

    def create_run(self, agent: str, phase: str, sections: Optional[list[str]] = None) -> str:
        """
        새 실행(run)을 생성하고 run_id를 반환한다.

        context_bus/runs.json에 기록.
        """
        from scripts.log_event import ensure_context_bus, get_workspace_path, load_json_array, save_json_array

        bus_dir = ensure_context_bus(self.workspace)
        runs_file = bus_dir / "runs.json"
        runs = load_json_array(runs_file)

        run_id = generate_run_id()
        runs.append(
            {
                "run_id": run_id,
                "started_at": utc_now(),
                "ended_at": None,
                "agents": [agent],
                "phases": [phase],
                "sections": sections or [],
                "events_count": 1,
                "outcome": None,
            }
        )
        save_json_array(runs_file, runs)
        return run_id

    def close_run(self, run_id: str, outcome: str = "success") -> None:
        """
        실행(run)을 종료 처리한다.
        """
        from scripts.log_event import ensure_context_bus, load_json_array, save_json_array

        bus_dir = ensure_context_bus(self.workspace)
        runs_file = bus_dir / "runs.json"
        runs = load_json_array(runs_file)

        for run in runs:
            if run.get("run_id") == run_id:
                run["ended_at"] = utc_now()
                run["outcome"] = outcome
                break
        save_json_array(runs_file, runs)


# ─────────────────────────────────────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────────────────────────────────────


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────────────────────────
# CLI 진입점
# ─────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python state_manager.py <workspace> [command] [args...]")
        print("Commands:")
        print("  get-phase           — 현재 Phase 출력")
        print("  add-issue <reason>  — Blocking Issue 추가")
        print("  list-issues         — Issue 목록 출력")
        print("  resolve <issue_id>  — Issue 해결")
        print("  gate-status <gate>  — 게이트 상태 출력")
        print("  sync                — 상태 파일 동기화")
        sys.exit(1)

    workspace = Path(sys.argv[1])
    sm = StateManager(workspace)

    if len(sys.argv) < 3:
        # 상태 요약 출력
        print(f"Project: {sm.get_project_id()}")
        print(f"Current Phase: {sm.get_current_phase()}")
        print(f"Phase Status: {sm.get_phase_status(sm.get_current_phase())}")
        unresolved = sm.get_blocking_issues(resolved=False)
        print(f"Unresolved Blocking Issues: {len(unresolved)}")
        for iss in unresolved:
            print(f"  {iss['issue_id']} | {iss['severity']} | {iss['reason']}")
        sys.exit(0)

    cmd = sys.argv[2]

    if cmd == "get-phase":
        print(sm.get_current_phase())

    elif cmd == "add-issue":
        reason = sys.argv[3] if len(sys.argv) > 3 else "Unspecified"
        issue_id = sm.add_blocking_issue({"reason": reason, "severity": "medium"})
        sm.sync()
        print(f"Issue added: {issue_id}")

    elif cmd == "list-issues":
        for iss in sm.get_blocking_issues():
            status = "RESOLVED" if iss.get("resolved") else "OPEN"
            print(f"{iss['issue_id']} [{status}] {iss['severity']} | {iss['reason']}")

    elif cmd == "resolve":
        issue_id = sys.argv[3] if len(sys.argv) > 3 else None
        if not issue_id:
            print("Error: issue_id required")
            sys.exit(1)
        sm.resolve_blocking_issue(issue_id, resolved_by="cli")
        sm.sync()
        print(f"Issue resolved: {issue_id}")

    elif cmd == "gate-status":
        gate = sys.argv[3] if len(sys.argv) > 3 else "P2_to_P3"
        status = sm.get_gate_status(gate)
        if not status:
            print(f"Gate '{gate}': not found (auto gate)")
        else:
            print(f"Gate '{gate}': {status.get('status')} | type={status.get('approval_type')}")
            print(f"  Required: {status.get('required_approvers')}")
            print(f"  Current:  {status.get('current_approvers')}")

    elif cmd == "sync":
        sm.sync()
        print("Sync complete")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
