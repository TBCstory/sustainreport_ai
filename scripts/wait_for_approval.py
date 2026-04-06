#!/usr/bin/env python3.13
"""
wait_for_approval.py — 게이트 승인 대기 핸들러

역할:
1. approval_gates.json에 대기 중 상태 기록
2. 사용자에게 승인 요청 (CLI 입력 또는 파일 기반)
3. 승인 시 approval_gates.json 갱신
4. 거부 시 blocking_issue 추가

승인 방식:
- CLI: 터미널에서 y/n 입력
- 파일 기반: approval_gates.json을 편집기로 직접 수정
- API (후순위): REST API로 승인 요청 수신

사용법:
    from scripts.wait_for_approval import wait_for_approval
    result = wait_for_approval(
        workspace="/path/to/PRJ-YYYY-CODE-NNN",
        gate_name="P2_to_P3",
        required_approvers=["project_manager", "consultant_lead"],
    )
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.state_manager import StateManager, normalize_approval_gates_data

# ─────────────────────────────────────────────────────────────────────────────
# 경로 상수
# ─────────────────────────────────────────────────────────────────────────────

APPROVAL_FILE = "approval_gates.json"


# ─────────────────────────────────────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ApprovalResult:
    """승인 결과."""

    gate_name: str
    decision: str  # "approved" | "rejected" | "timeout"
    approvers: list[str]
    elapsed_seconds: float
    message: str


# ─────────────────────────────────────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────────────────────────────────────


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_approval_gates(workspace: Path) -> dict:
    """approval_gates.json 로드."""
    path = workspace / APPROVAL_FILE
    if not path.exists():
        return normalize_approval_gates_data({}, project_id=workspace.name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return normalize_approval_gates_data(data, project_id=workspace.name)
    except (json.JSONDecodeError, OSError):
        return normalize_approval_gates_data({}, project_id=workspace.name)


def save_approval_gates(workspace: Path, data: dict) -> None:
    """approval_gates.json 저장."""
    path = workspace / APPROVAL_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_approval_gates_data(data, project_id=workspace.name)
    normalized["updated_at"] = utc_now()
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_gate_info(gate_name: str, gate_entry: dict) -> str:
    """게이트 정보를 포맷팅."""
    lines = [
        f"Gate: {gate_name}",
        f"Status: {gate_entry.get('status', 'unknown')}",
        f"Required approvers: {gate_entry.get('required_approvers', [])}",
        f"Current approvers: {[a['approver'] for a in gate_entry.get('current_approvers', [])]}",
        f"Requested at: {gate_entry.get('requested_at', '?')}",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# CLI 승인 처리
# ─────────────────────────────────────────────────────────────────────────────


def request_cli_approval(
    gate_name: str,
    required_approvers: list[str],
    timeout_seconds: Optional[int] = None,
) -> ApprovalResult:
    """
    CLI로 사용자에게 승인 요청.

    Args:
        gate_name: 게이트 ID
        required_approvers: 필요한 승인자 목록
        timeout_seconds: 타임아웃 (초). None이면 무한 대기.

    Returns:
        ApprovalResult
    """
    print("\n" + "=" * 60)
    print(f"⏳ 게이트 승인 요청: {gate_name}")
    print("=" * 60)
    print(f"필요한 승인자: {', '.join(required_approvers)}")
    print()
    print("승인 방식:")
    print("  1. 이 터미널에서 승인 (y) 또는 거부 (n)")
    print("  2. 다른 터미널에서 approval_gates.json 직접 편집")
    print()
    if timeout_seconds:
        print(f"타임아웃: {timeout_seconds}초")
    else:
        print("타임아웃: 없음 (Ctrl+C로 중단)")
    print("=" * 60)

    start_time = time.monotonic()
    elapsed = 0

    while True:
        remaining = f" (남은 시간: {timeout_seconds - elapsed:.0f}초)" if timeout_seconds else ""
        try:
            response = input(f"\n승인 (y) / 거부 (n) / 새로고침 (r){remaining}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n\n승인 요청이 중단되었습니다.")
            return ApprovalResult(
                gate_name=gate_name,
                decision="timeout",
                approvers=[],
                elapsed_seconds=time.monotonic() - start_time,
                message="User interrupted",
            )

        elapsed = time.monotonic() - start_time

        if response in ("y", "yes"):
            approver_name = input("승인자 이름을 입력하세요: ").strip()
            if not approver_name:
                approver_name = "cli_user"
            print(f"\n✅ '{gate_name}' 게이트가 '{approver_name}'에 의해 승인되었습니다.")
            return ApprovalResult(
                gate_name=gate_name,
                decision="approved",
                approvers=[approver_name],
                elapsed_seconds=elapsed,
                message=f"Approved by {approver_name}",
            )

        elif response in ("n", "no"):
            rejector_name = input("거부자 이름을 입력하세요: ").strip()
            if not rejector_name:
                rejector_name = "cli_user"
            print(f"\n❌ '{gate_name}' 게이트가 '{rejector_name}'에 의해 거부되었습니다.")
            return ApprovalResult(
                gate_name=gate_name,
                decision="rejected",
                approvers=[rejector_name],
                elapsed_seconds=elapsed,
                message=f"Rejected by {rejector_name}",
            )

        elif response == "r":
            # 새로고침 (파일 상태 확인)
            print("(파일 상태를 확인하려면 'r' 대신 approval_gates.json을 확인하세요)")
            continue

        else:
            print("올바른 입력이 아닙니다. y(승인), n(거부), r(새로고침)을 입력하세요.")
            if timeout_seconds and elapsed >= timeout_seconds:
                return ApprovalResult(
                    gate_name=gate_name,
                    decision="timeout",
                    approvers=[],
                    elapsed_seconds=elapsed,
                    message=f"Timed out after {elapsed:.0f} seconds",
                )


def poll_file_approval(
    workspace: Path,
    gate_name: str,
    timeout_seconds: Optional[int] = None,
    poll_interval: int = 10,
) -> ApprovalResult:
    """
    파일 상태를 폴링하여 승인 여부를 확인.

    Args:
        workspace: 워크스페이스 경로
        gate_name: 게이트 ID
        timeout_seconds: 최대 대기 시간
        poll_interval: 폴링 간격 (초)

    Returns:
        ApprovalResult
    """
    start_time = time.monotonic()
    elapsed = 0

    print(f"[wait_for_approval] Polling approval file every {poll_interval}s...")

    while True:
        data = load_approval_gates(workspace)
        gate_entry = data.get("gates", {}).get(gate_name)

        if gate_entry:
            status = gate_entry.get("status")
            if status == "approved":
                approvers = [a["approver"] for a in gate_entry.get("current_approvers", [])]
                return ApprovalResult(
                    gate_name=gate_name,
                    decision="approved",
                    approvers=approvers,
                    elapsed_seconds=time.monotonic() - start_time,
                    message="Approved via file update",
                )
            elif status == "rejected":
                rejector = gate_entry.get("decided_by", "unknown")
                return ApprovalResult(
                    gate_name=gate_name,
                    decision="rejected",
                    approvers=[rejector] if rejector else [],
                    elapsed_seconds=time.monotonic() - start_time,
                    message=f"Rejected via file update by {rejector}",
                )

        elapsed = time.monotonic() - start_time
        if timeout_seconds and elapsed >= timeout_seconds:
            return ApprovalResult(
                gate_name=gate_name,
                decision="timeout",
                approvers=[],
                elapsed_seconds=elapsed,
                message=f"Timed out after {elapsed:.0f} seconds",
            )

        remaining = timeout_seconds - elapsed if timeout_seconds else None
        wait_msg = f"Waiting... ({elapsed:.0f}s elapsed)"
        if remaining:
            wait_msg += f", {remaining:.0f}s remaining"
        print(f"[wait_for_approval] {wait_msg}")

        sleep_time = min(poll_interval, remaining) if remaining else poll_interval
        if sleep_time <= 0:
            break
        time.sleep(sleep_time)

    return ApprovalResult(
        gate_name=gate_name,
        decision="timeout",
        approvers=[],
        elapsed_seconds=time.monotonic() - start_time,
        message="Timed out",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 메인 함수
# ─────────────────────────────────────────────────────────────────────────────


def wait_for_approval(
    workspace: str | Path,
    gate_name: str,
    required_approvers: Optional[list[str]] = None,
    state_manager: Optional[StateManager] = None,
    timeout_seconds: Optional[int] = None,
    mode: str = "auto",  # "auto" | "cli" | "file"
) -> ApprovalResult:
    """
    게이트 승인을 기다린다.

    Args:
        workspace: 워크스페이스 경로
        gate_name: 게이트 ID
        required_approvers: 필요한 승인자 목록
        state_manager: StateManager 인스턴스
        timeout_seconds: 최대 대기 시간 (초). None이면 무한.
        mode: "auto" (CLI 먼저), "cli" (CLI 만), "file" (파일 폴링만)

    Returns:
        ApprovalResult
    """
    workspace = Path(workspace)
    required_approvers = required_approvers or []

    # StateManager로 게이트 대기 상태 설정
    if state_manager is None:
        try:
            state_manager = StateManager(workspace)
        except Exception:
            state_manager = None

    if state_manager and not state_manager.is_gate_waiting(gate_name):
        state_manager.wait_for_approval(
            gate_name=gate_name,
            required_approvers=required_approvers,
            requester="wait_for_approval",
        )

    # 모드에 따른 처리
    if mode == "cli":
        return request_cli_approval(gate_name, required_approvers, timeout_seconds)

    if mode == "file":
        return poll_file_approval(workspace, gate_name, timeout_seconds)

    # auto 모드: CLI 먼저, 파일 폴링으로 백업
    # 1. 먼저 CLI로 시도
    print("[wait_for_approval] Mode: auto (CLI first, file polling backup)")
    cli_result = request_cli_approval(gate_name, required_approvers, timeout_seconds=60)

    if cli_result.decision in ("approved", "rejected"):
        # CLI에서 결졍됨 → 파일에 기록
        _record_decision(workspace, gate_name, cli_result, state_manager)
        return cli_result

    # CLI에서 타임아웃 → 파일 폴링 모드로 전환
    print("[wait_for_approval] CLI timed out, switching to file polling mode...")
    remaining_timeout = None
    if timeout_seconds:
        remaining_timeout = timeout_seconds - int(cli_result.elapsed_seconds)

    return poll_file_approval(workspace, gate_name, remaining_timeout)


def _record_decision(
    workspace: Path,
    gate_name: str,
    result: ApprovalResult,
    state_manager: Optional[StateManager],
) -> None:
    """승인/거부 결정을 파일에 기록."""
    state_manager = state_manager or StateManager(workspace)

    if not state_manager.get_gate_status(gate_name):
        state_manager.wait_for_approval(
            gate_name=gate_name,
            required_approvers=[],
            requester="wait_for_approval",
        )

    # StateManager 연동
    for approver in result.approvers:
        state_manager.record_approval(
            gate_name=gate_name,
            approver=approver,
            signature=f"wait_for_approval-{utc_now()}",
            decision=result.decision,
        )
    # 거부 시 blocking issue 추가
    if result.decision == "rejected":
        state_manager.add_blocking_issue(
            issue={
                "reason": f"Gate '{gate_name}' rejected by {result.approvers[0] if result.approvers else 'unknown'}",
                "severity": "blocker",
                "gate": gate_name,
            },
            agent="wait_for_approval",
        )
        state_manager.sync()


# ─────────────────────────────────────────────────────────────────────────────
# CLI 진입점
# ─────────────────────────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--workspace",
    "-w",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="워크스페이스 경로",
)
@click.option(
    "--gate",
    "-g",
    required=True,
    help="게이트 ID (e.g., P2_to_P3)",
)
@click.option(
    "--approvers",
    "-a",
    multiple=True,
    help="필요한 승인자 (여러 개 가능)",
)
@click.option(
    "--timeout",
    "-t",
    type=int,
    default=None,
    help="타임아웃 (초). 없으면 무한 대기.",
)
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["auto", "cli", "file"]),
    default="auto",
    help="승인 대기 모드",
)
def main(
    workspace: Path,
    gate: str,
    approvers: tuple[str, ...],
    timeout: Optional[int],
    mode: str,
) -> int:
    """게이트 승인 대기 CLI."""
    required = list(approvers) if approvers else []

    print(f"[wait_for_approval] Starting...")
    print(f"  workspace: {workspace}")
    print(f"  gate: {gate}")
    print(f"  required_approvers: {required}")
    print(f"  timeout: {timeout}")
    print(f"  mode: {mode}")

    result = wait_for_approval(
        workspace=workspace,
        gate_name=gate,
        required_approvers=required,
        timeout_seconds=timeout,
        mode=mode,
    )

    print()
    print("=" * 60)
    print(f"결과: {result.decision.upper()}")
    print(f"게이트: {result.gate_name}")
    print(f"승인자: {result.approvers}")
    print(f"경과 시간: {result.elapsed_seconds:.1f}초")
    print(f"메시지: {result.message}")
    print("=" * 60)

    if result.decision == "approved":
        return 0
    elif result.decision == "rejected":
        return 1
    else:  # timeout
        return 2


if __name__ == "__main__":
    sys.exit(main())
