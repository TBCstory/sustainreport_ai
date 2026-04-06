#!/usr/bin/env python3.13
"""
run_fact_checker.py — P5 외부 검증 스크립트

역할:
1. section_writer 출력 (초안) + 원본 파일 읽기
2. fact-checker 에이전트 호출
3. 08_review/fact_check_report.json 생성

사용법:
    from scripts.run_fact_checker import run_fact_checker
    result = run_fact_checker("/path/to/PRJ-YYYY-CODE-NNN")
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.dispatch_agent import AgentDispatcher
from scripts.log_event import log_event
from scripts.state_manager import StateManager


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_draft_metas(workspace: Path) -> list[dict]:
    """07_drafts/SEC-*_meta.json 파일들을 로드."""
    drafts_dir = workspace / "07_drafts"
    metas = []

    if not drafts_dir.is_dir():
        return metas

    for meta_file in drafts_dir.glob("SEC-*_meta.json"):
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            data["_meta_file"] = str(meta_file.relative_to(workspace))
            metas.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return metas


def load_segment_manifest(workspace: Path) -> dict:
    """04_segments/segment_manifest.json 로드."""
    path = workspace / "04_segments" / "segment_manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_file_registry(workspace: Path) -> dict:
    """02_file_registry/file_registry.json 로드."""
    path = workspace / "02_file_registry" / "file_registry.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def build_context_for_fact_checker(
    workspace: Path,
    draft_metas: list[dict],
    segment_manifest: dict,
    file_registry: dict,
) -> dict:
    """
    fact-checker 에이전트에 전달할 컨텍스트를 구축한다.
    """
    # source_conflicts가 있는 초안 우선 추출
    conflict_sections = []
    all_sections = []

    for meta in draft_metas:
        section_id = meta.get("section_id", "unknown")
        source_conflicts = meta.get("source_conflicts", [])

        if source_conflicts:
            conflict_sections.append(
                {
                    "section_id": section_id,
                    "conflicts": source_conflicts,
                    "draft_file": meta.get("_meta_file", ""),
                }
            )

        all_sections.append(
            {
                "section_id": section_id,
                "draft_confidence": meta.get("draft_confidence"),
                "placeholder_count": meta.get("placeholder_count", 0),
            }
        )

    # 전체 세그먼트 수
    total_segments = segment_manifest.get("total_segments", 0)

    # 등록된 파일 수
    total_files = len(file_registry.get("files", []))

    return {
        "workspace": str(workspace),
        "total_sections": len(draft_metas),
        "conflict_sections": conflict_sections,
        "all_sections": all_sections,
        "total_segments": total_segments,
        "total_files": total_files,
        "draft_metas": draft_metas,
        "segment_manifest": segment_manifest,
        "file_registry": file_registry,
    }


def run_fact_checker(
    workspace: str | Path,
    section_ids: Optional[list[str]] = None,
) -> dict:
    """
    P5 외부 검증 (fact-checker)을 실행한다.

    Args:
        workspace: 워크스페이스 경로
        section_ids: 특정 섹션만 검증할 경우 (None이면 전체)

    Returns:
        {
            "success": bool,
            "outputs": list[str],
            "message": str,
            "report_path": str,
        }
    """
    workspace = Path(workspace)
    outputs = []

    # StateManager 초기화
    state_manager = StateManager(workspace)

    # 상태 파일 로드
    draft_metas = load_draft_metas(workspace)
    segment_manifest = load_segment_manifest(workspace)
    file_registry = load_file_registry(workspace)

    if not draft_metas:
        return {
            "success": False,
            "outputs": [],
            "message": "초안 메타 파일이 없습니다. P4 section-writer를 먼저 실행하세요.",
            "report_path": "",
        }

    # 섹션 필터링
    if section_ids:
        section_id_set = set(section_ids)
        draft_metas = [m for m in draft_metas if m.get("section_id") in section_id_set]

    # 컨텍스트 구축
    context = build_context_for_fact_checker(
        workspace=workspace,
        draft_metas=draft_metas,
        segment_manifest=segment_manifest,
        file_registry=file_registry,
    )

    # Dispatcher 초기화
    dispatcher = AgentDispatcher(workspace=workspace, state_manager=state_manager)

    # 출력 파일
    output_files = ["08_review/fact_check_report.json"]

    # fact-checker 에이전트 호출
    result = dispatcher.dispatch(
        agent="fact-checker",
        context=context,
        output_files=output_files,
    )

    # 결과 처리
    report_path = workspace / "08_review" / "fact_check_report.json"

    # Report content validation (detect non-JSON or agent error messages)
    report_valid = False
    if report_path.exists():
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
            report_valid = "fact_check_report_version" in data or "findings" in data
        except (json.JSONDecodeError, OSError):
            report_valid = False

    if result.success and report_valid:
        outputs.append(str(report_path.relative_to(workspace)))

        # 리포트 내용에서 요약 추출
        try:
            report_data = json.loads(report_path.read_text(encoding="utf-8"))
            findings_count = len(report_data.get("findings", []))
            critical_errors = sum(1 for f in report_data.get("findings", []) if f.get("severity") == "critical")
            message = f"P5 팩트체크 완료: {findings_count}개 발견사항, critical={critical_errors}"
        except (json.JSONDecodeError, OSError):
            message = "P5 팩트체크 완료 (리포트 파싱 실패)"

        state_manager.sync()

        # 로그 이벤트
        log_event(
            event_type="progress",
            agent="fact-checker",
            phase="P5",
            message=message,
            workspace=str(workspace),
        )

        return {
            "success": True,
            "outputs": outputs,
            "message": message,
            "report_path": str(report_path.relative_to(workspace)),
        }

    else:
        # 실패 시 폴백 리포트 생성
        fallback_report = {
            "fact_check_report_version": "1.0",
            "generated_at": utc_now(),
            "workspace": str(workspace),
            "sections_checked": len(draft_metas),
            "findings": [],
            "status": "fallback_generated",
            "note": "fact-checker 에이전트 호출 실패로 자동 생성된 폴백 리포트",
        }

        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(fallback_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        outputs.append(str(report_path.relative_to(workspace)))

        return {
            "success": False,
            "outputs": outputs,
            "message": f"fact-checker 호출 실패: {result.error}",
            "report_path": str(report_path.relative_to(workspace)),
            "fallback": True,
        }


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
    "--section",
    "-s",
    "section_ids",
    multiple=True,
    help="특정 섹션만 검증 (SEC-X.Y.Z)",
)
def main(workspace: Path, section_ids: tuple[str, ...]) -> int:
    """P5 외부 검증 (fact-checker) 실행."""
    print(f"[run_fact_checker] P5 팩트체크 시작")
    print(f"  workspace: {workspace}")
    if section_ids:
        print(f"  sections: {list(section_ids)}")
    else:
        print(f"  sections: all")

    result = run_fact_checker(
        workspace=workspace,
        section_ids=list(section_ids) if section_ids else None,
    )

    print()
    if result["success"]:
        print(f"✅ {result['message']}")
        print(f"   Report: {result['report_path']}")
        return 0
    else:
        print(f"⚠️  {result['message']}")
        print(f"   Report: {result['report_path']} (fallback)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
