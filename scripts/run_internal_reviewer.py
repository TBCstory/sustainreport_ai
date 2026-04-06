#!/usr/bin/env python3.13
"""
run_internal_reviewer.py — P5 내부 검수 스크립트

역할:
1. section-writer 출력 (초안) 읽기
2. internal-reviewer 에이전트 호출
3. 08_review/internal_review_report.json 생성

사용법:
    from scripts.run_internal_reviewer import run_internal_reviewer
    result = run_internal_reviewer("/path/to/PRJ-YYYY-CODE-NNN")
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
    """07_drafts/SEC-*_meta.json 파일들 로드."""
    drafts_dir = workspace / "07_drafts"
    if not drafts_dir.is_dir():
        return []

    metas = []
    for meta_file in drafts_dir.glob("SEC-*_meta.json"):
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            data["_meta_file"] = str(meta_file.relative_to(workspace))
            metas.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return metas


def load_writing_blueprint(workspace: Path) -> dict:
    """05_planning/writing_blueprint.json 로드."""
    path = workspace / "05_planning" / "writing_blueprint.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_structure_index(workspace: Path) -> dict:
    """05_planning/structure_index.json 로드."""
    path = workspace / "05_planning" / "structure_index.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_terminology_dictionary() -> dict:
    """guidance/terminology_dictionary.json 로드."""
    path = PROJECT_ROOT / "guidance" / "terminology_dictionary.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_style_guide() -> dict:
    """guidance/style_guide.json 로드."""
    path = PROJECT_ROOT / "guidance" / "style_guide.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def build_review_context(
    workspace: Path,
    draft_metas: list[dict],
    writing_blueprint: dict,
    structure_index: dict,
    terminology: dict,
    style_guide: dict,
) -> dict:
    """internal-reviewer에 전달할 컨텍스트 구축."""
    # 섹션별 confidence 요약
    section_confidences = []
    placeholder_counts = []
    issue_counts = []

    for meta in draft_metas:
        section_id = meta.get("section_id", "unknown")
        confidence = meta.get("draft_confidence", 0.0)
        placeholders = meta.get("placeholders", [])
        issues = meta.get("issues", [])

        section_confidences.append({"section_id": section_id, "confidence": confidence})
        placeholder_counts.append({"section_id": section_id, "count": len(placeholders)})
        issue_counts.append({"section_id": section_id, "count": len(issues)})

    # 구조 인덱스 정보
    structure_entries = structure_index.get("entries", [])

    # 블루프린트 섹션 깊이 정보
    blueprint_sections = writing_blueprint.get("sections", [])

    return {
        "workspace": str(workspace),
        "draft_metas_count": len(draft_metas),
        "section_confidences": section_confidences,
        "placeholder_counts": placeholder_counts,
        "issue_counts": issue_counts,
        "structure_index_entries_count": len(structure_entries),
        "blueprint_sections_count": len(blueprint_sections),
        "writing_blueprint": writing_blueprint,
        "structure_index": structure_index,
        "terminology": terminology,
        "style_guide": style_guide,
    }


def run_internal_reviewer(
    workspace: str | Path,
    state_manager=None,
) -> dict:
    """
    P5 내부 검수를 실행한다.

    Args:
        workspace: 워크스페이스 경로

    Returns:
        {"success": bool, "outputs": list[str], "message": str, "report_path": str}
    """
    workspace = Path(workspace)
    outputs = []

    # StateManager 초기화
    state_manager = StateManager(workspace)

    # 입력 파일 로드
    draft_metas = load_draft_metas(workspace)
    writing_blueprint = load_writing_blueprint(workspace)
    structure_index = load_structure_index(workspace)
    terminology = load_terminology_dictionary()
    style_guide = load_style_guide()

    if not draft_metas:
        return {
            "success": False,
            "outputs": [],
            "message": "초안 메타 파일이 없습니다. P4 section-writer를 먼저 실행하세요.",
            "report_path": None,
        }

    # 컨텍스트 구축
    context = build_review_context(
        workspace=workspace,
        draft_metas=draft_metas,
        writing_blueprint=writing_blueprint,
        structure_index=structure_index,
        terminology=terminology,
        style_guide=style_guide,
    )

    # Dispatcher 초기화
    dispatcher = AgentDispatcher(workspace=workspace, state_manager=state_manager)

    # output 경로
    review_dir = workspace / "08_review"
    review_dir.mkdir(parents=True, exist_ok=True)
    report_path = review_dir / "internal_review_report.json"

    # internal-reviewer 에이전트 호출
    result = dispatcher.dispatch(
        agent="internal-reviewer",
        context=context,
        output_files=["08_review/internal_review_report.json"],
    )

    # Report content validation (detect agent error messages vs real reports)
    report_valid = False
    report_file = workspace / "08_review" / "internal_review_report.json"
    if report_file.exists():
        try:
            data = json.loads(report_file.read_text())
            has_sections = len(data.get("reviewed_sections", [])) > 0
            has_confidence = data.get("overall_confidence") is not None
            report_valid = ("review_phase" in data or "report_version" in data) and (has_sections or has_confidence)
        except (json.JSONDecodeError, OSError):
            report_valid = False

    if result.success and report_valid:
        outputs.append("08_review/internal_review_report.json")

        # 상태 갱신
        state_manager.sync()

        # 로그 이벤트
        log_event(
            event_type="milestone",
            agent="internal-reviewer",
            phase="P5",
            message=f"P5 내부 검수 완료: {len(draft_metas)}개 섹션 검수됨",
            workspace=str(workspace),
        )

        return {
            "success": True,
            "outputs": outputs,
            "message": f"P5 내부 검수 완료: {len(draft_metas)}개 섹션 검수",
            "report_path": str(report_path.relative_to(workspace)),
        }
    else:
        # 실패 시 폴백 보고서 생성
        fallback_report = _generate_fallback_report(workspace, draft_metas)
        report_path.write_text(
            json.dumps(fallback_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        outputs.append("08_review/internal_review_report.json")

        return {
            "success": True,
            "outputs": outputs,
            "message": f"P5 내부 검수 완료 (폴백): {len(draft_metas)}개 섹션",
            "report_path": str(report_path.relative_to(workspace)),
            "fallback": True,
        }


def _generate_fallback_report(workspace: Path, draft_metas: list[dict]) -> dict:
    """LLM 호출 실패 시 폴백 검수 보고서 생성."""
    issues_by_section = []
    total_issues = 0
    total_placeholders = 0

    for meta in draft_metas:
        section_id = meta.get("section_id", "unknown")
        placeholders = meta.get("placeholders", [])
        issues = meta.get("issues", [])

        total_placeholders += len(placeholders)
        total_issues += len(issues)

        issues_by_section.append(
            {
                "section_id": section_id,
                "issue_count": len(issues),
                "placeholder_count": len(placeholders),
                "confidence": meta.get("draft_confidence", 0.0),
                "issues": issues[:5],  # 최대 5개만
            }
        )

    avg_confidence = sum(m.get("draft_confidence", 0.0) for m in draft_metas) / len(draft_metas) if draft_metas else 0.0

    return {
        "report_version": "1.0",
        "report_type": "internal_review",
        "generated_at": utc_now(),
        "source": "fallback (agent unavailable)",
        "summary": {
            "total_sections_reviewed": len(draft_metas),
            "total_issues_found": total_issues,
            "total_placeholders": total_placeholders,
            "average_confidence": round(avg_confidence, 2),
            "review_score": round(avg_confidence, 2),
        },
        "issues_by_section": issues_by_section,
        "terminology_issues": [],
        "structural_issues": [],
        "placeholder_alerts": [
            {"section_id": iss["section_id"], "count": iss["placeholder_count"]}
            for iss in issues_by_section
            if iss["placeholder_count"] >= 5
        ],
        "recommendations": [
            "내부 검수 실패: evidence 기반 검수가 필요합니다",
            "section-writer 출력물을 수동 검수해주세요",
        ],
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
def main(workspace: Path) -> int:
    """P5 내부 검수 스크립트."""
    print(f"[run_internal_reviewer] P5 내부 검수 시작")
    print(f"  workspace: {workspace}")

    result = run_internal_reviewer(workspace=workspace)

    print()
    if result["success"]:
        print(f"✅ {result['message']}")
        print(f"   Report: {result['report_path']}")
        print(f"   Outputs: {result['outputs']}")
        return 0
    else:
        print(f"❌ {result['message']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
