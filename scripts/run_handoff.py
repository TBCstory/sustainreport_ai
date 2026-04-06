#!/usr/bin/env python3.13
"""
run_handoff.py — P6 초안 정리 및 핸드오프 스크립트

역할:
1. 모든 검수 완료 초안 읽기
2. draft_package.json 생성
3. 09_handoff/에 최종 초안 복사
4. 핸드오프 메타데이터 구성

사용법:
    from scripts.run_handoff import run_handoff
    result = run_handoff("/path/to/PRJ-YYYY-CODE-NNN")
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.log_event import log_event
from scripts.state_manager import StateManager


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_meta_field(meta: dict, canonical: str, aliases: list[str], default=None):
    """정규 키를 먼저 읽고, 없으면 alias 순서로 시도."""
    val = meta.get(canonical)
    if val is not None:
        return val
    for alias in aliases:
        val = meta.get(alias)
        if val is not None:
            return val
    return default


def _normalize_confidence(value) -> Optional[float]:
    """confidence 값을 숫자(0-1)로 정규화. 문자열 매핑 지원."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        mapping = {"high": 0.85, "medium": 0.55, "low": 0.25, "very_low": 0.1}
        result = mapping.get(value.lower(), 0.5)
        if value.lower() not in mapping:
            import sys

            print(f"[run_handoff] WARNING: unknown confidence string '{value}', using 0.5", file=sys.stderr)
        return result
    return 0.5


def _extract_placeholder_strings(placeholders) -> list[str]:
    """placeholders 필드에서 문자열 배열을 추출. 객체 배열도 지원."""
    if not placeholders:
        return []
    if isinstance(placeholders, list) and len(placeholders) > 0:
        first = placeholders[0]
        if isinstance(first, str):
            return placeholders
        if isinstance(first, dict):
            return [p.get("placeholder", p.get("location", "")) for p in placeholders if isinstance(p, dict)]
    return []


def _calc_review_priority(meta: dict) -> float:
    """높을수록 먼저 검토 필요. 0-100 scale."""
    score = 0.0
    confidence = _normalize_confidence(meta.get("draft_confidence") or meta.get("confidence"))
    if confidence is not None:
        score += (1.0 - confidence) * 40
    placeholders = _extract_placeholder_strings(meta.get("placeholders") or meta.get("placeholders_inserted", []))
    score += min(len(placeholders) * 5, 30)
    missing = meta.get("missing_evidence") or []
    score += min(len(missing) * 5, 20)
    evidence = meta.get("evidence_segments") or meta.get("evidence_segments_used") or []
    if not evidence:
        score += 10
    return round(min(score, 100), 1)


def load_review_reports(workspace: Path) -> dict:
    """08_review/에서 검수 보고서 로드."""
    reports = {}

    internal_report_path = workspace / "08_review" / "internal_review_report.json"
    if internal_report_path.exists():
        try:
            reports["internal_review"] = json.loads(internal_report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            reports["internal_review"] = {}

    fact_check_path = workspace / "08_review" / "fact_check_report.json"
    if fact_check_path.exists():
        try:
            reports["fact_check"] = json.loads(fact_check_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            reports["fact_check"] = {}

    return reports


def load_draft_metas(workspace: Path) -> list[dict]:
    """07_drafts/SEC-*_meta.json 파일들 로드."""
    drafts_dir = workspace / "07_drafts"
    if not drafts_dir.is_dir():
        return []

    metas = []
    for meta_file in sorted(drafts_dir.glob("SEC-*_meta.json")):
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            data["_meta_file"] = str(meta_file.relative_to(workspace))
            metas.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return metas


def load_draft_files(workspace: Path) -> list[Path]:
    """07_drafts/SEC-*.md 파일 목록."""
    drafts_dir = workspace / "07_drafts"
    if not drafts_dir.is_dir():
        return []
    return sorted(drafts_dir.glob("SEC-*.md"))


def load_structure_index(workspace: Path) -> dict:
    """structure_index.json 로드."""
    path = workspace / "05_planning" / "structure_index.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def copy_drafts_to_handoff(
    workspace: Path,
    handoff_dir: Path,
    draft_files: list[Path],
    draft_metas: list[dict],
) -> list[str]:
    """
    검수 완료된 초안을 09_handoff/ 디렉토리로 복사.

    Returns:
        복사된 파일 경로 목록 (workspace 상대경로)
    """
    outputs = []
    meta_map = {m.get("section_id"): m for m in draft_metas}

    for draft_file in draft_files:
        section_id = draft_file.stem  # e.g. "SEC-3.1"
        meta = meta_map.get(section_id, {})

        # 대상 디렉토리: 09_handoff/drafts/
        draft_subdir = handoff_dir / "drafts"
        draft_subdir.mkdir(parents=True, exist_ok=True)

        dest_path = draft_subdir / draft_file.name
        shutil.copy2(draft_file, dest_path)
        outputs.append(str(dest_path.relative_to(workspace)))

        # 메타도 함께 복사
        meta_source = workspace / "07_drafts" / f"{section_id}_meta.json"
        if meta_source.exists():
            meta_dest = draft_subdir / f"{section_id}_meta.json"
            shutil.copy2(meta_source, meta_dest)

    return outputs


def build_draft_package(
    workspace: Path,
    draft_metas: list[dict],
    review_reports: dict,
    structure_index: dict,
    handoff_dir: Path,
) -> dict:
    """
    draft_package.json 생성.

    핸드오프 패키지 메타데이터 구성:
    - 프로젝트 개요
    - 섹션별 초안 목록 + 신뢰도
    - 검수 결과 요약
    - 다음 행동建议
    """
    # 섹션 신뢰도 요약
    section_summary = []
    for meta in sorted(draft_metas, key=lambda m: m.get("section_id", "")):
        section_id = meta.get("section_id", "unknown")
        # PKT-B005: normalize confidence before comparison (draft_confidence may be string "low"/"medium"/"high")
        confidence_raw = meta.get("draft_confidence", meta.get("confidence_score", 0.0))
        confidence = _normalize_confidence(confidence_raw)
        if confidence is None:
            confidence = 0.0
        placeholders = meta.get("placeholder_count", 0)
        source_tag_count = meta.get("source_tag_count", 0)

        status = "approved" if (isinstance(confidence, (int, float)) and confidence >= 0.8) else "needs_review"
        if placeholders > 5:
            status = "needs_work"

        section_summary.append(
            {
                "section_id": section_id,
                "draft_version": meta.get("draft_version", 1),
                "confidence": confidence,
                "placeholder_count": placeholders,
                "source_tag_count": source_tag_count,
                "status": status,
                "fallback_mode": meta.get("fallback_mode", False),
                "draft_file": f"drafts/{section_id}.md",
                "meta_file": f"drafts/{section_id}_meta.json",
                # OD-6: Enrich with full evidence metadata arrays
                "missing_evidence": meta.get("missing_evidence", [])[:3],
                "client_confirmation_needed": meta.get("client_confirmation_needed", [])[:3],
                "source_conflicts": meta.get("source_conflicts", [])[:3],
                "placeholders_inserted": meta.get("placeholders_inserted", [])[:5],
                "kpi_status_summary": meta.get("kpi_status_summary", {}),
            }
        )

    # 검수 결과 요약
    review_summary = {
        "internal_review": {
            "status": "complete" if review_reports.get("internal_review") else "not_run",
            "sections_reviewed": review_reports.get("internal_review", {})
            .get("summary", {})
            .get("total_sections_reviewed", 0),
            "average_confidence": review_reports.get("internal_review", {})
            .get("summary", {})
            .get("average_confidence", 0.0),
        },
        "fact_check": {
            "status": "complete" if review_reports.get("fact_check") else "not_run",
            "findings_count": len(review_reports.get("fact_check", {}).get("findings", [])),
        },
    }

    # 구조 인덱스 정보
    structure_entries = structure_index.get("entries", [])

    # 다음 행동
    pending_sections = [s for s in section_summary if s["status"] in ("needs_review", "needs_work")]
    next_actions = []
    if pending_sections:
        next_actions.append(
            {
                "priority": "high",
                "action": f"{len(pending_sections)}개 섹션 재검토 필요",
                "sections": [s["section_id"] for s in pending_sections],
            }
        )

    # 신뢰도较低的 섹션
    low_confidence = [s for s in section_summary if s["confidence"] < 0.6]
    if low_confidence:
        next_actions.append(
            {
                "priority": "medium",
                "action": "신뢰도 낮은 섹션 증거 보강 필요",
                "sections": [s["section_id"] for s in low_confidence],
            }
        )

    package = {
        "package_version": "1.0",
        "package_type": "handoff",
        "generated_at": utc_now(),
        "workspace": str(workspace),
        "project": {
            "project_id": workspace.name,
            "structure_index_entries": len(structure_entries),
            "structure_entries": structure_entries,
        },
        "sections": section_summary,
        "review_summary": review_summary,
        "statistics": {
            "total_sections": len(section_summary),
            "approved": sum(1 for s in section_summary if s["status"] == "approved"),
            "needs_review": sum(1 for s in section_summary if s["status"] == "needs_review"),
            "needs_work": sum(1 for s in section_summary if s["status"] == "needs_work"),
            "average_confidence": round(sum(s["confidence"] for s in section_summary) / len(section_summary), 2)
            if section_summary
            else 0.0,
            "total_placeholders": sum(s["placeholder_count"] for s in section_summary),
            "fallback_mode_sections": sum(1 for s in section_summary if s.get("fallback_mode", False)),
        },
        "next_actions": next_actions,
        "handoff_checklist": [
            {"item": "초안 신뢰도 0.8 이상 섹션 우선 검토", "done": False},
            {"item": "placeholder 5개 이상 섹션 증거 보강", "done": False},
            {"item": "프레임워크 공시 항목 완료 여부 확인", "done": False},
            {"item": "용어 일관성 최종 검토", "done": False},
            {"item": "컨설턴트 최종 승인", "done": False},
        ],
    }

    return package


def build_framework_indexing_readiness(
    workspace: Path,
    draft_metas: list[dict],
    structure_index: dict,
    handoff_dir: Path,
) -> dict:
    """
    framework_indexing_readiness.json 생성.

    OD-6: 프레임워크 인덱싱 준비 상태를 보여주는 메타데이터 파일.
    참조: purrfect-riding-blossom.md §3.6
    """
    entries = structure_index.get("entries", [])
    structure_section_ids = {e.get("section_id") for e in entries}

    # Draft artifact refs
    draft_section_ids = {meta.get("section_id") for meta in draft_metas}
    meta_map = {meta.get("section_id"): meta for meta in draft_metas}

    # Framework mappings from structure_index
    all_framework_mappings = []
    for entry in entries:
        for fm in entry.get("framework_mappings", []):
            all_framework_mappings.append(
                {
                    "section_id": entry.get("section_id"),
                    "framework": fm.get("framework", ""),
                    "disclosure": fm.get("disclosure", ""),
                    "coverage_type": fm.get("coverage_type", ""),
                }
            )

    # Anchor completeness
    anchor_missing_sections = []
    for entry in entries:
        sid = entry.get("section_id", "")
        if not entry.get("heading_anchor"):
            anchor_missing_sections.append(
                {
                    "section_id": sid,
                    "heading_text": entry.get("heading_text", ""),
                    "reason": "heading_anchor 미등록",
                }
            )

    # Draft linkage
    unlinked_anchors = []
    for entry in entries:
        sid = entry.get("section_id", "")
        if sid not in draft_section_ids:
            unlinked_anchors.append(
                {
                    "section_id": sid,
                    "reason": "draft 미생성",
                }
            )

    # Unmapped disclosures (have framework mappings but section is in fallback/placeholder)
    unmapped_disclosures = []
    for entry in entries:
        sid = entry.get("section_id", "")
        if entry.get("framework_mappings") and sid in meta_map:
            meta = meta_map[sid]
            if meta.get("fallback_mode", False) or meta.get("placeholder_count", 0) > 0:
                for fm in entry.get("framework_mappings", []):
                    unmapped_disclosures.append(
                        {
                            "framework": fm.get("framework", ""),
                            "disclosure": fm.get("disclosure", ""),
                            "section_id": sid,
                            "status": "placeholder_only",
                            "reason": "본문이 placeholder만으로 구성",
                        }
                    )

    # Placeholder-only sections (non-fallback but has placeholders)
    placeholder_only_disclosures = []
    for meta in draft_metas:
        sid = meta.get("section_id", "")
        if meta.get("placeholder_count", 0) > 0 and not meta.get("fallback_mode", False):
            placeholders = meta.get("placeholders_inserted", [])
            placeholder_count = len(placeholders)
            if placeholder_count > 0:
                placeholder_only_disclosures.append(
                    {
                        "section_id": sid,
                        "reason": f"본문에 placeholder {placeholder_count}건 포함",
                        "placeholder_count": placeholder_count,
                    }
                )

    # Manual review required items
    manual_review_required_items = []
    if anchor_missing_sections:
        for item in anchor_missing_sections[:2]:
            manual_review_required_items.append(
                {
                    "item": f"{item['section_id']} 앵커 미등록 — 구조 설계 보완 필요",
                    "priority": "high",
                }
            )
    if unmapped_disclosures:
        for item in unmapped_disclosures[:2]:
            manual_review_required_items.append(
                {
                    "item": f"{item['framework']} {item['disclosure']} 매핑 누락 — 해당 섹션 지정 필요",
                    "priority": "medium",
                }
            )
    if placeholder_only_disclosures:
        for item in placeholder_only_disclosures[:2]:
            manual_review_required_items.append(
                {
                    "item": f"{item['section_id']} placeholder {item['placeholder_count']}건 — 본문 보완 후 인덱싱 가능",
                    "priority": "medium",
                }
            )

    # Compute coverage rate
    mapped_sections = sum(1 for e in entries if e.get("framework_mappings"))
    total_disclosures = len(all_framework_mappings)
    coverage_rate = round(mapped_sections / len(entries), 3) if entries else 0.0

    # Overall status determination
    if not anchor_missing_sections and not unlinked_anchors and not unmapped_disclosures:
        overall_status = "ready"
    elif not unlinked_anchors and placeholder_only_disclosures:
        overall_status = "ready_with_placeholders"
    else:
        overall_status = "partially_ready"

    readiness = {
        "overall_status": overall_status,
        "summary": {
            "mappable_sections_count": mapped_sections,
            "total_sections": len(entries),
            "total_disclosures_required": total_disclosures,
            "total_disclosures_mapped": mapped_sections,
            "coverage_rate": coverage_rate,
        },
        "anchor_completeness": {
            "all_sections_have_anchor": len(anchor_missing_sections) == 0,
            "anchor_missing_sections": anchor_missing_sections[:5],
        },
        "draft_linkage": {
            "all_anchors_linked_to_drafts": len(unlinked_anchors) == 0,
            "unlinked_anchors": unlinked_anchors[:5],
        },
        "unmapped_disclosures": unmapped_disclosures[:10],
        "placeholder_only_disclosures": placeholder_only_disclosures[:10],
        "manual_review_required_items": manual_review_required_items[:10],
    }

    # Write to handoff dir
    readiness_path = handoff_dir / "framework_indexing_readiness.json"
    readiness_path.write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return readiness


def generate_handoff_summary_md(
    workspace: Path,
    package: dict,
    handoff_dir: Path,
    draft_queries: list[dict],
    structure_index: dict,
) -> Path:
    """
    handoff_summary.md 생성 — 사람이 읽기 좋은 섹션별 요약.

    Args:
        workspace: 워크스페이스 경로
        package: build_draft_package() 결과
        handoff_dir: 09_handoff/ 디렉토리
        draft_queries: draft_queries.json의 queries 리스트

    Returns:
        생성된 파일 경로
    """
    lines: list[str] = []
    lines.append(f"# 핸드오프 요약 — {workspace.name}")
    lines.append("")
    lines.append(f"> 생성일: {package.get('generated_at', '')}")
    lines.append("")

    # ── 통계 요약 ──────────────────────────────────────────────
    stats = package.get("statistics", {})
    sections = package.get("sections", [])
    approved = stats.get("approved", 0)
    needs_review = stats.get("needs_review", 0)
    needs_work = stats.get("needs_work", 0)
    total_placeholders = stats.get("total_placeholders", 0)
    avg_conf = stats.get("average_confidence", 0.0)

    lines.append("## 프로젝트 요약")
    lines.append("")
    lines.append(f"| 지표 | 값 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 총 섹션 수 | {stats.get('total_sections', 0)} |")
    lines.append(f"| 승인 완료 | {approved} |")
    lines.append(f"| 검토 필요 | {needs_review} |")
    lines.append(f"| 작업 필요 | {needs_work} |")
    lines.append(f"| 평균 신뢰도 | {avg_conf} |")
    lines.append(f"| 총 플레이스홀더 | {total_placeholders} |")
    lines.append("")

    # ── 섹션별 초안 상태 ───────────────────────────────────────
    lines.append("## 섹션별 초안 상태")
    lines.append("")
    lines.append("| 섹션 ID | 제목 | 신뢰도 | 플레이스홀더 | 상태 |")
    lines.append("|---------|------|--------|-------------|------|")

    # Build title map from structure_index entries
    title_map: dict[str, str] = {}
    for entry in structure_index.get("entries", []):
        title_map[entry.get("section_id", "")] = entry.get("heading_text", "")

    for sec in sections:
        sid = sec.get("section_id", "")
        title = title_map.get(sid, "")
        conf = sec.get("confidence", 0.0)
        ph = sec.get("placeholder_count", 0)
        status = sec.get("status", "unknown")
        conf_str = f"{conf:.0%}" if conf else "—"
        status_badge = {
            "approved": "✅ 승인",
            "needs_review": "⚠️ 검토 필요",
            "needs_work": "🔴 작업 필요",
        }.get(status, status)
        lines.append(f"| {sid} | {title} | {conf_str} | {ph} | {status_badge} |")

    lines.append("")

    # ── 재검토 권장 섹션 ──────────────────────────────────────
    review_sections = [s for s in sections if s.get("status") in ("needs_review", "needs_work")]
    if review_sections:
        lines.append("## 재검토 권장 섹션")
        lines.append("")
        for sec in review_sections:
            sid = sec.get("section_id", "")
            title = title_map.get(sid, "")
            conf = sec.get("confidence", 0.0)
            ph = sec.get("placeholder_count", 0)
            lines.append(f"- **{sid}** {title}")
            lines.append(f"  - 신뢰도: {conf:.0%} | 플레이스홀더: {ph}개")
        lines.append("")

    # ── Open Query 요약 ──────────────────────────────────────
    if draft_queries:
        lines.append("## 미해결 Query (Open Queries)")
        lines.append("")
        open_queries = [q for q in draft_queries if q.get("status") == "open"]
        if open_queries:
            lines.append(f"총 **{len(open_queries)}개** open query가 있습니다.")
            lines.append("")
            for q in sorted(open_queries, key=lambda x: x.get("priority", "medium")):
                qid = q.get("query_id", "?")
                sid = q.get("section_id", "?")
                priority = q.get("priority", "medium")
                question = q.get("question", q.get("description", ""))
                priority_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
                lines.append(f"- [{qid}] {priority_icon} **{sid}**: {question}")
        else:
            lines.append("open query가 없습니다.")
        lines.append("")

    # ── 다음 행동 ─────────────────────────────────────────────
    next_actions = package.get("next_actions", [])
    if next_actions:
        lines.append("## 다음 행동")
        lines.append("")
        for na in next_actions:
            priority = na.get("priority", "medium")
            action = na.get("action", "")
            secs = na.get("sections", [])
            priority_icon = {"high": "🔴", "medium": "🟡"}.get(priority, "⚪")
            lines.append(f"- {priority_icon} **{action}**")
            if secs:
                lines.append(f"  - 해당 섹션: {', '.join(secs)}")
        lines.append("")

    # ── 체크리스트 ─────────────────────────────────────────────
    checklist = package.get("handoff_checklist", [])
    if checklist:
        lines.append("## 핸드오프 체크리스트")
        lines.append("")
        for item in checklist:
            done = "☑️" if item.get("done") else "☐"
            lines.append(f"{done} {item.get('item', '')}")
        lines.append("")

    summary_path = handoff_dir / "handoff_summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


# ── PKT-A005: 핸드오프 품질 강화 산출물 생성 ──────────────────────────────────


def _generate_placeholder_summary(workspace: Path, outputs: list[str]) -> None:
    """
    09_handoff/placeholder_summary.md 생성.
    섹션별 placeholder 수, 신뢰도 점수, 확인 필요 항목을 표로 정리.
    """
    import re

    drafts_dir = workspace / "07_drafts"
    handoff_dir = workspace / "09_handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)

    PLACEHOLDER_PATTERNS = [
        r"\[확인필요\]",
        r"\[데이터 없음\]",
        r"\[TBD\]",
        r"\[PLACEHOLDER\]",
        r"\[추후 기재\]",
        r"\[미확인\]",
        r"\[자료 부족\]",
    ]
    placeholder_re = re.compile("|".join(PLACEHOLDER_PATTERNS))

    rows = []
    meta_files = sorted(drafts_dir.glob("SEC-*_meta.json"))

    for meta_path in meta_files:
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        section_id = meta.get("section_id", meta_path.stem.replace("_meta", ""))
        heading = _read_meta_field(meta, "heading_ko", ["heading_text", "section_title", "title"], "(제목 없음)")
        confidence = _normalize_confidence(
            _read_meta_field(meta, "draft_confidence", ["confidence_score", "confidence"], None)
        )
        # placeholders 필드에서 문자열 추출 (객체 배열/문자열 배열 모두 지원)
        placeholders_raw = _read_meta_field(meta, "placeholders", ["placeholders_inserted"], [])
        placeholder_strings = _extract_placeholder_strings(placeholders_raw)
        # MD 파일에서 추가 placeholder 탐지 (정규식 기반)
        draft_md = drafts_dir / f"{section_id}.md"
        md_placeholder_count = 0
        if draft_md.exists():
            content = draft_md.read_text(encoding="utf-8")
            md_placeholder_count = len(placeholder_re.findall(content))
        # 정규화된 placeholders + MD 탐지 결과 중 큰 값
        placeholder_count = max(len(placeholder_strings), md_placeholder_count)

        rows.append(
            {
                "section_id": section_id,
                "heading": heading,
                "confidence": confidence,
                "placeholder_count": placeholder_count,
                "placeholder_list": placeholder_strings[:5],  # 표에는 최대 5개만
            }
        )

    # 마크다운 표 생성
    total_placeholders = sum(r["placeholder_count"] for r in rows)

    lines = [
        "# Placeholder 요약표",
        "",
        f"> 생성일시: {utc_now()}  ",
        f"> 전체 placeholder: **{total_placeholders}개**",
        "",
        "| 섹션 ID | 제목 | 신뢰도 | Placeholder 수 | 주요 placeholder (상위 5개) |",
        "|---------|------|--------|---------------|---------------------------|",
    ]

    for r in sorted(rows, key=lambda x: x["placeholder_count"], reverse=True):
        confidence_str = f"{r['confidence']:.1%}" if r["confidence"] is not None else "—"
        placeholder_preview = ", ".join(r["placeholder_list"]) if r["placeholder_list"] else "—"
        lines.append(
            f"| {r['section_id']} | {r['heading']} | {confidence_str} | "
            f"{r['placeholder_count']} | {placeholder_preview} |"
        )

    lines += [
        "",
        "## 컨설턴트 안내",
        "",
        "- **Placeholder 수가 높은 섹션**부터 우선 검토하세요.",
        "- `[확인필요]` 표시는 원본 자료에서 직접 확인이 필요한 항목입니다.",
        "- Draft Query(`DQ-NNN`)는 `draft_queries.json`에서 상세 내용을 확인할 수 있습니다.",
    ]

    output_path = handoff_dir / "placeholder_summary.md"
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    outputs.append(str(output_path.relative_to(workspace)))


def _generate_data_gap_priority(workspace: Path, outputs: list[str]) -> None:
    """
    09_handoff/data_gap_priority.md 생성.
    증거 충족도가 낮은 섹션을 우선순위 순으로 표시.
    """
    handoff_dir = workspace / "09_handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir = workspace / "07_drafts"

    # 1. writing_blueprint에서 섹션 목록
    blueprint_path = workspace / "05_planning" / "writing_blueprint.json"
    blueprint_sections = {}
    if blueprint_path.exists():
        try:
            bp = json.loads(blueprint_path.read_text(encoding="utf-8"))
            for sec in bp.get("sections", []):
                sid = sec.get("section_id")
                if sid:
                    blueprint_sections[sid] = sec
        except (json.JSONDecodeError, KeyError):
            pass

    # 2. 버킷에서 섹션별 세그먼트 수
    buckets_dir = workspace / "06_buckets"
    bucket_counts: dict[str, int] = {}
    if buckets_dir.exists():
        for bucket_file in buckets_dir.glob("SEC-*.json"):
            try:
                data = json.loads(bucket_file.read_text(encoding="utf-8"))
                sid = data.get("section_id", bucket_file.stem)
                segments = data.get("grounded_segments", [])
                bucket_counts[sid] = len(segments)
            except (json.JSONDecodeError, KeyError):
                pass

    # 3. data_gap_report에서 변환 실패 파일
    gap_report_path = workspace / "02_file_registry" / "data_gap_report.json"
    unconvertible_files = []
    if gap_report_path.exists():
        try:
            gap = json.loads(gap_report_path.read_text(encoding="utf-8"))
            unconvertible_files = gap.get("unconvertible_files", [])
        except (json.JSONDecodeError, KeyError):
            pass

    # 4. 섹션별 충족도 계산
    gap_rows = []
    for sid, sec_info in blueprint_sections.items():
        required = sec_info.get("evidence_priority", "medium")
        actual_count = bucket_counts.get(sid, 0)
        heading = sec_info.get("heading_ko", sec_info.get("heading_text", "(제목 없음)"))

        # 간단한 충족도 판정
        if actual_count == 0:
            gap_level = "🔴 없음"
            priority = 1
        elif actual_count < 3:
            gap_level = "🟡 부족"
            priority = 2
        else:
            gap_level = "🟢 충분"
            priority = 3

        # Load meta for review_priority_score
        meta_path = drafts_dir / f"{sid}_meta.json"
        review_priority = 0.0
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                review_priority = _calc_review_priority(meta)
            except (json.JSONDecodeError, OSError):
                pass

        gap_rows.append(
            {
                "section_id": sid,
                "heading": heading,
                "evidence_priority": required,
                "actual_segments": actual_count,
                "gap_level": gap_level,
                "sort_priority": priority,
                "review_priority_score": review_priority,
            }
        )

    gap_rows.sort(key=lambda x: (-x["review_priority_score"], x["section_id"]))

    # 마크다운 생성
    lines = [
        "# 자료 부족 섹션 우선순위표",
        "",
        f"> 생성일시: {utc_now()}",
        "",
        "## 섹션별 증거 충족도",
        "",
        "| 검토점수 | 섹션 ID | 제목 | 증거 세그먼트 수 | 충족도 |",
        "|----------|---------|------|----------------|-------|",
    ]

    for r in gap_rows:
        lines.append(
            f"| {r['review_priority_score']:.1f} | {r['section_id']} | {r['heading']} | {r['actual_segments']} | {r['gap_level']} |"
        )

    if unconvertible_files:
        lines += [
            "",
            "## 변환 실패 파일 (자료 미반영)",
            "",
            "아래 파일은 변환에 실패하여 초안에 반영되지 않았습니다. 수동 변환 또는 대체 자료 제공이 필요합니다.",
            "",
            "| 파일 | 유형 | 오류 |",
            "|------|------|------|",
        ]
        for f in unconvertible_files:
            error_summary = (f.get("error") or "알 수 없는 오류")[:80]
            lines.append(f"| {f.get('source_path', '-')} | {f.get('file_type', '-')} | {error_summary} |")

    lines += [
        "",
        "## 컨설턴트 안내",
        "",
        "- **🔴 없음** 섹션은 증거 자료가 전무합니다. 해당 섹션 내용을 직접 작성하거나 자료를 추가로 제공해주세요.",
        "- **🟡 부족** 섹션은 보완이 권장됩니다.",
        "- **🟢 충분** 섹션은 검토 후 서술 품질만 확인하면 됩니다.",
    ]

    output_path = handoff_dir / "data_gap_priority.md"
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    outputs.append(str(output_path.relative_to(workspace)))


def _generate_consultant_review_checklist(workspace: Path, outputs: list[str]) -> None:
    """
    09_handoff/consultant_review_checklist.json 생성.
    우선순위 순으로 컨설턴트 확인 항목 목록.
    """
    handoff_dir = workspace / "09_handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)

    checklist_items = []

    # 1. draft_queries.json에서 미해결 질문 수집
    dq_path = workspace / "draft_queries.json"
    if dq_path.exists():
        try:
            dq_data = json.loads(dq_path.read_text(encoding="utf-8"))
            queries = dq_data if isinstance(dq_data, list) else dq_data.get("queries", [])
            for q in queries:
                if q.get("status") not in ("resolved", "closed"):
                    checklist_items.append(
                        {
                            "type": "draft_query",
                            "id": q.get("query_id", "DQ-???"),
                            "section_id": q.get("section_id"),
                            "priority": q.get("priority", "medium"),
                            "description": q.get("question", q.get("description", "")),
                            "action_required": "원본 자료에서 수치/사실 확인 후 [확인필요] 교체",
                            "status": "open",
                        }
                    )
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # 2. confidence_score < 0.5인 섹션 추가 (draft_confidence 정규 키 + alias fallback)
    drafts_dir = workspace / "07_drafts"
    for meta_path in sorted(drafts_dir.glob("SEC-*_meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            score = _normalize_confidence(
                _read_meta_field(meta, "draft_confidence", ["confidence_score", "confidence"], None)
            )
            heading = _read_meta_field(meta, "heading_ko", ["heading_text", "section_title", "title"], "")
            if score is not None and score < 0.5:
                checklist_items.append(
                    {
                        "type": "low_confidence_section",
                        "id": meta.get("section_id", meta_path.stem),
                        "section_id": meta.get("section_id"),
                        "priority": "high" if score < 0.3 else "medium",
                        "description": f"신뢰도 낮음: {score:.1%} — {heading}",
                        "action_required": "섹션 내용 전체 검토 및 부정확한 서술 수정",
                        "status": "open",
                    }
                )
            # 3. missing_evidence 3개 이상인 섹션
            missing = meta.get("missing_evidence") or []
            if len(missing) >= 3:
                checklist_items.append(
                    {
                        "type": "data_collection_needed",
                        "id": meta.get("section_id", meta_path.stem),
                        "section_id": meta.get("section_id"),
                        "priority": "high",
                        "description": f"미확보 증거 {len(missing)}개 — {heading}",
                        "action_required": "원본 자료에서 미확보 항목 직접 확인 및 초안에 반영",
                        "status": "open",
                    }
                )
            # 4. placeholders 5개 이상인 섹션
            placeholders_raw = _read_meta_field(meta, "placeholders", ["placeholders_inserted"], [])
            placeholder_strings = _extract_placeholder_strings(placeholders_raw)
            if len(placeholder_strings) >= 5:
                checklist_items.append(
                    {
                        "type": "heavy_placeholder_section",
                        "id": meta.get("section_id", meta_path.stem),
                        "section_id": meta.get("section_id"),
                        "priority": "medium",
                        "description": f"Placeholder {len(placeholder_strings)}개 — {heading}",
                        "action_required": "[확인필요] 항목 우선 확인 후 실제 데이터로 교체",
                        "status": "open",
                    }
                )
        except (json.JSONDecodeError, KeyError):
            continue

    # 3. 우선순위 정렬 (high > medium > low)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    checklist_items.sort(key=lambda x: priority_order.get(x.get("priority", "medium"), 1))

    output_data = {
        "generated_at": utc_now(),
        "total_items": len(checklist_items),
        "high_priority_count": sum(1 for x in checklist_items if x.get("priority") == "high"),
        "items": checklist_items[:50],  # Top 50
        "notes": [
            "이 목록은 초안 생성 시 자동으로 식별된 확인 필요 항목입니다.",
            "모든 항목을 해결한 후 최종 보고서를 완성하세요.",
            "draft_queries.json의 query_id를 해당 섹션 초안(07_drafts/SEC-*.md)에서 찾아 수정하세요.",
        ],
    }

    output_path = handoff_dir / "consultant_review_checklist.json"
    output_path.write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    outputs.append(str(output_path.relative_to(workspace)))


def run_handoff(
    workspace: str | Path,
    state_manager=None,
) -> dict:
    """
    P6 핸드오프 단계를 실행한다.

    Args:
        workspace: 워크스페이스 경로

    Returns:
        {
            "success": bool,
            "outputs": list[str],
            "message": str,
            "package_path": str,
        }
    """
    workspace = Path(workspace)
    outputs = []

    # StateManager 초기화
    state_manager = StateManager(workspace)

    # 핸드오프 디렉토리
    handoff_dir = workspace / "09_handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)

    # 1. 검수 보고서 로드
    review_reports = load_review_reports(workspace)

    # 2. 초안 파일 및 메타 로드
    draft_metas = load_draft_metas(workspace)
    draft_files = load_draft_files(workspace)

    if not draft_files:
        return {
            "success": False,
            "outputs": [],
            "message": "초안 파일이 없습니다. P4 section-writer를 먼저 실행하세요.",
            "package_path": None,
        }

    # 3. structure_index 로드
    structure_index = load_structure_index(workspace)

    # 4. 초안을 핸드오프 디렉토리로 복사
    copied_files = copy_drafts_to_handoff(workspace, handoff_dir, draft_files, draft_metas)
    outputs.extend(copied_files)

    # 5. draft_package.json 생성
    package = build_draft_package(
        workspace=workspace,
        draft_metas=draft_metas,
        review_reports=review_reports,
        structure_index=structure_index,
        handoff_dir=handoff_dir,
    )

    package_path = handoff_dir / "draft_package.json"
    package_path.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    outputs.append(str(package_path.relative_to(workspace)))

    # 6. handoff_summary.md 생성
    draft_queries = []
    dq_path = workspace / "draft_queries.json"
    if dq_path.exists():
        try:
            dq_data = json.loads(dq_path.read_text(encoding="utf-8"))
            draft_queries = dq_data.get("queries", []) if isinstance(dq_data, dict) else dq_data
        except (json.JSONDecodeError, OSError):
            pass

    summary_path = generate_handoff_summary_md(workspace, package, handoff_dir, draft_queries, structure_index)
    outputs.append(str(summary_path.relative_to(workspace)))

    # 7. framework_indexing_readiness.json 생성 (OD-6)
    readiness = build_framework_indexing_readiness(workspace, draft_metas, structure_index, handoff_dir)
    outputs.append(str(Path("09_handoff") / "framework_indexing_readiness.json"))

    # ── PKT-A005: 핸드오프 품질 강화 산출물 생성 ──
    try:
        _generate_placeholder_summary(workspace, outputs)
    except Exception as e:
        log_event("warning", "handoff", "P6", f"placeholder_summary.md 생성 실패: {e}", str(workspace))

    try:
        _generate_data_gap_priority(workspace, outputs)
    except Exception as e:
        log_event("warning", "handoff", "P6", f"data_gap_priority.md 생성 실패: {e}", str(workspace))

    try:
        _generate_consultant_review_checklist(workspace, outputs)
    except Exception as e:
        log_event("warning", "handoff", "P6", f"consultant_review_checklist.json 생성 실패: {e}", str(workspace))

    # 8. 상태 갱신
    state_manager.set_phase_status("P6", "complete")

    # OD-6: log framework indexing readiness summary
    log_event(
        event_type="milestone",
        agent="handoff",
        phase="P6",
        message=f"framework_indexing_readiness.json 생성됨: overall_status={readiness.get('overall_status')}, "
        f"coverage_rate={readiness.get('summary', {}).get('coverage_rate', 0.0)}",
        workspace=str(workspace),
    )
    state_manager.sync()

    # 8. 로그 이벤트
    log_event(
        event_type="milestone",
        agent="handoff",
        phase="P6",
        message=f"P6 핸드오프 완료: {len(draft_files)}개 초안 패키지화됨",
        workspace=str(workspace),
    )

    stats = package.get("statistics", {})
    message = (
        f"P6 핸드오프 완료: {stats.get('total_sections', 0)}개 섹션, "
        f"평균 신뢰도 {stats.get('average_confidence', 0.0)}, "
        f"placeholders {stats.get('total_placeholders', 0)}개"
    )

    return {
        "success": True,
        "outputs": outputs,
        "message": message,
        "package_path": str(package_path.relative_to(workspace)),
        "statistics": stats,
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
    """P6 핸드오프 스크립트."""
    print(f"[run_handoff] P6 핸드오프 시작")
    print(f"  workspace: {workspace}")
    print()

    result = run_handoff(workspace=workspace)

    print()
    if result["success"]:
        print(f"✅ {result['message']}")
        print(f"   Package: {result['package_path']}")
        stats = result.get("statistics", {})
        print(f"   Sections: {stats.get('total_sections', 0)}")
        print(f"     Approved    : {stats.get('approved', 0)}")
        print(f"     Needs review: {stats.get('needs_review', 0)}")
        print(f"     Needs work  : {stats.get('needs_work', 0)}")
        print(f"   Outputs: {result['outputs'][:6]}")
        if len(result["outputs"]) > 6:
            print(f"            ... +{len(result['outputs']) - 6} more files")
        return 0
    else:
        print(f"❌ {result['message']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
