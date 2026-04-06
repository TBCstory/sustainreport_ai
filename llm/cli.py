#!/usr/bin/env python3
"""
llm/cli.py — sustainreport AI CLI 진입점

Usage:
    sustainreport --help
    sustainreport init-workspace PRJ-2024-ABC-001
    sustainreport check-gate P2_to_P3 --workspace /path/to/PRJ-YYYY-CODE-NNN
    sustainreport update-state --workspace /path/to/PRJ-YYYY-CODE-NNN
    sustainreport run-ingestion /path/to/PRJ-YYYY-CODE-NNN
    sustainreport run-plan --workspace /path/to/PRJ-YYYY-CODE-NNN [--skip-approval]
    sustainreport run-draft --workspace /path/to/PRJ-YYYY-CODE-NNN [--section SEC-3.1]
    sustainreport run-pipeline --workspace /path/to/PRJ-YYYY-CODE-NNN [--start P0] [--end P7]
    sustainreport approve P2_to_P3 --workspace /path/to/PRJ-YYYY-CODE-NNN
    sustainreport status --workspace /path/to/PRJ-YYYY-CODE-NNN
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# init-workspace
# =============================================================================


@click.command("init-workspace")
@click.argument("project_id")
@click.option(
    "--base-path",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Base path for workspaces directory (default: ./workspaces)",
)
def cmd_init_workspace(project_id: str, base_path: Path | None) -> int:
    """새 프로젝트 워크스페이스 디렉토리를 생성한다."""
    from scripts.init_workspace import create_workspace

    try:
        path = create_workspace(project_id, base_path)
        click.echo(f"Workspace created: {path}")
        return 0
    except (ValueError, FileExistsError) as e:
        click.echo(f"Error: {e}", err=True)
        return 1
    except OSError as e:
        click.echo(f"OS Error: {e}", err=True)
        return 1


# =============================================================================
# check-gate
# =============================================================================


@click.command("check-gate")
@click.argument("gate")
@click.option(
    "--workspace",
    "-w",
    "workspace",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="워크스페이스 경로",
)
@click.option(
    "--from-phase",
    type=str,
    default=None,
    help="시작 페이즈 (auto 게이트용)",
)
@click.option(
    "--to-phase",
    type=str,
    default=None,
    help="종료 페이즈 (auto 게이트용)",
)
def cmd_check_gate(
    gate: str,
    workspace: Path,
    from_phase: str | None,
    to_phase: str | None,
) -> int:
    """게이트 조건을 평가한다."""
    import json

    from scripts.check_gate import GateEvaluator

    orchestration_dir = PROJECT_ROOT / "orchestration"
    evaluator = GateEvaluator(workspace=workspace, orchestration_dir=orchestration_dir)
    result = evaluator.evaluate(gate, from_phase, to_phase)

    click.echo(json.dumps(result, ensure_ascii=False, indent=2))

    if result["result"] == "passed":
        return 0
    elif result["result"] == "needs_human_approval":
        return 2
    else:
        return 1


# =============================================================================
# update-state
# =============================================================================


@click.command("update-state")
@click.option(
    "--workspace",
    "-w",
    "workspace",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="워크스페이스 경로",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="기존 project_state.json 무시하고 처음부터 생성",
)
def cmd_update_state(workspace: Path, force: bool) -> int:
    """project_state.json을 갱신한다."""
    from scripts.update_project_state import update_project_state

    try:
        state = update_project_state(workspace, force=force)
        click.echo(f"project_state.json updated: {workspace / 'project_state.json'}")
        click.echo(f"  project_id:    {state['project_id']}")
        click.echo(f"  current_phase: {state['current_phase']}")
        return 0
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        return 1
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        return 1


# =============================================================================
# run-ingestion
# =============================================================================


@click.command("run-ingestion")
@click.argument("workspace", type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path))
@click.option(
    "--files",
    "-f",
    nargs="*",
    help="변환할 파일 목록 (생략 시 01_raw/에서 자동 수집)",
)
def cmd_run_ingestion(workspace: Path, files: list[str] | None) -> int:
    """P1 자료 투입을 실행한다 (정규화 + 세그먼트 추출)."""
    from scripts.run_ingestion import run_ingestion

    result = run_ingestion(
        workspace=workspace,
        file_paths=files,
    )

    click.echo("=== P1 Ingestion Result ===")
    click.echo(f"Files processed : {result['files_processed']}")
    click.echo(f"  Success       : {result['files_success']}")
    click.echo(f"  Failed         : {result['files_failed']}")
    click.echo(f"Segments created: {result['segments_created']}")
    click.echo(f"Outputs         : {result['outputs']}")
    if result["errors"]:
        click.echo("Errors:")
        for err in result["errors"]:
            click.echo(f"  - {err}")

    return 0 if result["success"] else 1


# =============================================================================
# run-plan
# =============================================================================


@click.command("run-plan")
@click.option(
    "--workspace",
    "-w",
    "workspace",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="워크스페이스 경로",
)
@click.option(
    "--skip-approval",
    is_flag=True,
    default=False,
    help="P2→P3 게이트 승인 건너뛰기 (테스트용)",
)
def cmd_run_plan(workspace: Path, skip_approval: bool) -> int:
    """P2 기획을 실행한다 (structure_index, writing_blueprint, section_manifest 생성)."""
    from scripts.run_toc_planner import run_toc_planner

    result = run_toc_planner(
        workspace=str(workspace),
        skip_approval=skip_approval,
    )

    # waiting 상태가 먼저 확인 (success=True + waiting=True일 수 있음)
    if result.get("waiting"):
        click.echo(f"P2 completed — awaiting approval")
        click.echo(f"  Outputs: {result['outputs']}")
        click.echo(f"  Message: {result['message']}")
        click.echo(f"  Gate: {result.get('gate_name', 'P2_to_P3')} (status: waiting)")
        return 2  # Waiting for approval — caller should poll or present to human

    if result["success"]:
        click.echo(f"P2 completed successfully")
        click.echo(f"  Outputs: {result['outputs']}")
        click.echo(f"  Message: {result['message']}")
        return 0
    else:
        click.echo(f"P2 failed", err=True)
        click.echo(f"  Message: {result['message']}", err=True)
        return 1


# =============================================================================
# run-draft
# =============================================================================


@click.command("run-draft")
@click.option(
    "--workspace",
    "-w",
    "workspace",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="워크스페이스 경로",
)
@click.option(
    "--section",
    "-s",
    "section_ids",
    multiple=True,
    help="작성할 섹션 ID (예: SEC-3.1). 생략 시 전체 섹션.",
)
@click.option(
    "--no-parallel",
    is_flag=True,
    default=False,
    help="섹션 병렬 처리 비활성화",
)
@click.option(
    "--max-workers",
    type=int,
    default=4,
    help="병렬 처리 최대 워커 수 (default: 4)",
)
def cmd_run_draft(
    workspace: Path,
    section_ids: tuple[str, ...],
    no_parallel: bool,
    max_workers: int,
) -> int:
    """P4 초안 작성을 실행한다."""
    from scripts.run_section_writer import run_section_writer

    result = run_section_writer(
        workspace=str(workspace),
        section_ids=list(section_ids) if section_ids else None,
        parallel=not no_parallel,
        max_workers=max_workers,
    )

    if result["success"]:
        click.echo(f"{result['message']}")
        click.echo(f"  Sections written: {result['sections_written']}/{result['total_sections']}")
        click.echo(f"  Outputs: {result['outputs'][:6]}")
        if len(result["outputs"]) > 6:
            click.echo(f"            ... +{len(result['outputs']) - 6} more files")
        return 0
    else:
        click.echo(f"{result['message']}", err=True)
        if result.get("failed_sections"):
            click.echo(f"  Failed sections: {result['failed_sections']}", err=True)
        return 1


# =============================================================================
# run-pipeline
# =============================================================================


@click.command("run-pipeline")
@click.option(
    "--workspace",
    "-w",
    "workspace",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="워크스페이스 경로",
)
@click.option(
    "--start",
    "start_phase",
    type=str,
    default="P0",
    help="시작 페이즈 (default: P0)",
)
@click.option(
    "--end",
    "end_phase",
    type=str,
    default="P7",
    help="종료 페이즈 (default: P7)",
)
@click.option(
    "--skip-approvals",
    is_flag=True,
    default=False,
    help="모든 게이트 승인 건너뛰기 (테스트용)",
)
@click.option(
    "--no-parallel",
    is_flag=True,
    default=False,
    help="섹션 병렬 처리 비활성화",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="실행 없이 게이트 상태만 확인",
)
def cmd_run_pipeline(
    workspace: Path,
    start_phase: str,
    end_phase: str,
    skip_approvals: bool,
    no_parallel: bool,
    dry_run: bool,
) -> int:
    """P0→P7 전체 또는 범위 파이프라인을 실행한다."""
    from scripts.run_pipeline import PipelineEngine
    from scripts.update_project_state import build_project_state_snapshot

    print(f"=== Pipeline Run ===")
    print(f"Workspace : {workspace}")
    print(f"Range    : {start_phase} → {end_phase}")
    print(f"Mode     : {'TEST (skip approvals)' if skip_approvals else 'NORMAL'}")
    print(f"Dry-run  : {dry_run}")
    print()

    if dry_run:
        from scripts.check_gate import GateEvaluator

        PHASE_ORDER = ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7"]
        NEXT_PHASE = {"P0": "P1", "P1": "P2", "P2": "P3", "P3": "P4", "P4": "P5", "P5": "P6", "P6": "P7"}

        orchestration_dir = PROJECT_ROOT / "orchestration"
        gate_eval = GateEvaluator(workspace=workspace, orchestration_dir=orchestration_dir)
        live_state = build_project_state_snapshot(workspace)
        current_phase = live_state.get("current_phase", start_phase)
        try:
            start_index = PHASE_ORDER.index(start_phase)
            current_index = PHASE_ORDER.index(current_phase)
            end_index = PHASE_ORDER.index(end_phase)
        except ValueError as e:
            click.echo(f"Invalid phase: {e}", err=True)
            return 1

        effective_start_index = max(start_index, current_index)
        effective_start = PHASE_ORDER[effective_start_index]

        print("Gate Status Check:")
        print(f"  Current phase: {current_phase}")
        print(f"  Effective range: {effective_start} → {end_phase}")

        if effective_start_index >= end_index:
            print("  No forward transitions in the requested range.")
            return 0

        for phase in PHASE_ORDER[effective_start_index:end_index]:
            next_phase = NEXT_PHASE.get(phase)
            gate_name = f"{phase}_to_{next_phase}"
            if gate_name in ("P2_to_P3", "P5_to_P6"):
                result = gate_eval.evaluate(gate_name)
            else:
                result = gate_eval.evaluate_auto_gate(phase, next_phase)
            print(f"  {gate_name}: {result['result']}")
            if result["result"] != "passed":
                break
        return 0

    engine = PipelineEngine(
        workspace=workspace,
        skip_approvals=skip_approvals,
        parallel_sections=not no_parallel,
        start_phase=start_phase,
        end_phase=end_phase,
        section_ids=None,
    )

    try:
        result = engine.run()
        engine.print_summary(result)

        # HD-4: pipeline 후 현재 상태 narrative 자동 출력
        try:
            from scripts.update_project_state import generate_narrative_status

            narrative = generate_narrative_status(workspace)
            if narrative:
                click.echo("\n--- Current Status ---")
                click.echo(narrative)
        except Exception:
            pass  # status 출력 실패가 exit code에 영향 주면 안 됨

        return 0 if result.success else 1
    except Exception as e:
        click.echo(f"Pipeline error: {e}", err=True)
        return 1


# =============================================================================
# approve
# =============================================================================


@click.command("approve")
@click.argument("gate")
@click.option(
    "--workspace",
    "-w",
    "workspace",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="워크스페이스 경로",
)
@click.option(
    "--by",
    "approver_name",
    type=str,
    default=None,
    help="승인자 이름 (기본값: current user)",
)
@click.option(
    "--notes",
    type=str,
    default="",
    help="승인 메모",
)
def cmd_approve(gate: str, workspace: Path, approver_name: str | None, notes: str) -> int:
    """게이트 승인을 기록한다.

    지원 게이트: P2_to_P3, P5_to_P6
    """
    import getpass
    from datetime import datetime, timezone

    from scripts.state_manager import StateManager

    state_manager = StateManager(workspace)
    gate_info = state_manager.get_gate_status(gate)
    if gate_info is None:
        available = list(state_manager._approval_gates.get("gates", {}).keys())
        click.echo(f"Error: unknown gate '{gate}'. Available: {available}", err=True)
        return 1

    if not gate_info.get("approval_type") == "human":
        click.echo(
            f"Gate '{gate}' is not a human-approval gate (approval_type={gate_info.get('approval_type')})", err=True
        )
        return 1

    if approver_name is None:
        approver_name = getpass.getuser()

    recorded = state_manager.record_approval(
        gate_name=gate,
        approver=approver_name,
        signature=f"cli-approve:{approver_name}",
        decision="approved",
        notes=notes or None,
    )
    gate_info = state_manager.get_gate_status(gate) or gate_info
    required = gate_info.get("required_approvers", [])
    current_approvers = {entry.get("approver") for entry in gate_info.get("current_approvers", [])}
    all_approved = gate_info.get("status") == "approved"

    if not recorded:
        click.echo(f"Gate '{gate}' is already {gate_info.get('status')}", err=True)
        return 1

    click.echo(f"Gate '{gate}' approval recorded for '{approver_name}'")

    if all_approved:
        click.echo(f"  -> Gate '{gate}' is now fully approved")

        # Also update writing_blueprint.json approved field when P2_to_P3 is fully approved
        if gate == "P2_to_P3":
            bp_path = workspace / "05_planning" / "writing_blueprint.json"
            if bp_path.exists():
                bp = json.loads(bp_path.read_text(encoding="utf-8"))
                bp["approved"] = True
                bp["approved_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                bp_path.write_text(json.dumps(bp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                click.echo(f"  -> writing_blueprint.json approved flag updated")
    else:
        still_needed = [r for r in required if r not in current_approvers]
        click.echo(f"  -> Still needed: {still_needed}")

    return 0


# =============================================================================
# status
# =============================================================================


@click.command("status")
@click.option(
    "--workspace",
    "-w",
    "workspace",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="워크스페이스 경로",
)
def cmd_status(workspace: Path) -> int:
    """프로젝트 상태 요약을 출력한다.

    current phase, blockers, open queries, next actions (≤3), blueprint approval status를
    자연어 블록으로 표시한다. OD-7 자연어 UX 서피스.
    """
    from scripts.update_project_state import generate_narrative_status

    try:
        narrative = generate_narrative_status(workspace)
        click.echo(narrative)
    except Exception as e:
        click.echo(f"Error generating status: {e}", err=True)
        return 1

    return 0


# =============================================================================
# Click group & main
# =============================================================================


@click.group()
@click.version_option(version="0.1.0")
def main() -> int:
    """sustainreport AI — ESG 지속가능경영보고서 초안 생성 시스템"""
    # Propagate exit code from subcommand
    return 0


@main.result_callback()
def propagate_exit_code(result: int) -> None:
    """Propagate subcommand exit code as main's exit code."""
    sys.exit(result)


# Register commands
main.add_command(cmd_init_workspace, name="init-workspace")
main.add_command(cmd_check_gate, name="check-gate")
main.add_command(cmd_update_state, name="update-state")
main.add_command(cmd_run_ingestion, name="run-ingestion")
main.add_command(cmd_run_plan, name="run-plan")
main.add_command(cmd_run_draft, name="run-draft")
main.add_command(cmd_run_pipeline, name="run-pipeline")
main.add_command(cmd_approve, name="approve")
main.add_command(cmd_status, name="status")


if __name__ == "__main__":
    sys.exit(main())
