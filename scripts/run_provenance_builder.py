#!/usr/bin/env python3.13
"""
run_provenance_builder.py — P7 증거 체인 구축 스크립트

역할:
1. section_writer + internal_reviewer + fact_checker 출력 읽기
2. provenance-builder 에이전트 호출 (실제 evidence가 있을 때만)
3. 10_evidence_pack/evidence_chain.json + metadata.json + readme.md 생성

사용법:
    from scripts.run_provenance_builder import run_provenance_builder
    result = run_provenance_builder("/path/to/PRJ-YYYY-CODE-NNN")
"""

from __future__ import annotations

import hashlib
import json
import re
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
    metas = []

    if not drafts_dir.is_dir():
        return metas

    for meta_file in sorted(drafts_dir.glob("SEC-*_meta.json")):
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


def load_internal_review_report(workspace: Path) -> dict:
    """08_review/internal_review_report.json 로드."""
    path = workspace / "08_review" / "internal_review_report.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_fact_check_report(workspace: Path) -> dict:
    """08_review/fact_check_report.json 로드."""
    path = workspace / "08_review" / "fact_check_report.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _is_fallback_mode(draft_metas: list[dict]) -> bool:
    """
    모든 draft가 fallback mode인지 판정.

    조건: 모든 draft meta의 fallback_mode=true 이고 source_tags가 모두 비어있음.
    이런 경우 provenance-builder LLM을 호출해도 할루시네이션만 발생하므로
    폴백 경로를 직접 사용한다.
    """
    if not draft_metas:
        return True

    for meta in draft_metas:
        # fallback_mode=true이면 해당 섹션은 evidence 없는 상태
        if not meta.get("fallback_mode", False):
            # 하나라도 evidence 기반 섹션이 있으면 non-fallback
            return False

        # fallback_mode=true이라도 source_tags가 비어있어야 완전한 폴백
        source_tags = meta.get("source_tags", [])
        if source_tags:
            # source_tags가 있으면 evidence 추적이 가능하므로 non-fallback
            return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# OD-10: paragraph_provenance_map generator
# ─────────────────────────────────────────────────────────────────────────────

PARAGRAPH_SPLITTER = re.compile(r"\n\n+")
_PROVENANCE_TAG_RE = re.compile(r"<!--\s*src:SEG-\d+[@v\d]*\s*-->|<!--\s*src:CALC-\d+\s*-->", re.IGNORECASE)
_MARKDOWN_HEADER_RE = re.compile(r"^#{1,6}\s+")


def _compute_text_hash(text: str) -> str:
    """Compute SHA256 hex digest of text, truncated to 16 chars for readability."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _load_draft_body(workspace: Path, section_id: str) -> str:
    """Load draft markdown body for a section (without front-matter)."""
    draft_path = workspace / "07_drafts" / f"{section_id}.md"
    if not draft_path.exists():
        return ""
    try:
        content = draft_path.read_text(encoding="utf-8")
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                content = content[end + 3 :].strip()
        return content
    except (OSError, UnicodeDecodeError):
        return ""


def _extract_segment_refs_from_paragraph(para: str) -> list[str]:
    """Extract all SEG-*/CALC-* refs from a paragraph string."""
    return [m.group(0) for m in _PROVENANCE_TAG_RE.finditer(para)]


def _is_header_only_paragraph(content_for_check: str) -> bool:
    """Return True if paragraph consists only of markdown header lines."""
    lines = [ln.strip() for ln in content_for_check.splitlines() if ln.strip()]
    return bool(lines) and all(_MARKDOWN_HEADER_RE.match(ln) for ln in lines)


def _build_paragraph_provenance_map(workspace: Path, draft_metas: list[dict]) -> dict:
    """
    Build paragraph_provenance_map.json — §3.3 OD-10 deliverable.

    Scans every draft paragraph, records whether it has a provenance tag,
    and maps it to source segment refs.

    Output shape matches §3.3 lightweight paragraph-tracking requirement.
    """
    provenance_map = {}

    for meta in draft_metas:
        section_id = meta.get("section_id", "")
        if not section_id:
            continue

        body = _load_draft_body(workspace, section_id)
        if not body:
            continue

        paragraphs = PARAGRAPH_SPLITTER.split(body)
        for idx, para in enumerate(paragraphs):
            stripped = para.strip()
            if not stripped:
                continue

            # Remove anchor tags for checking (not provenance evidence)
            content_for_check = re.sub(r"<!--\s*anchor:[^\s]+\s*-->", "", stripped)
            content_for_check = re.sub(r"^---$", "", content_for_check, flags=re.MULTILINE)

            # Skip header-only paragraphs (provenance not required)
            if _is_header_only_paragraph(content_for_check):
                continue

            seg_refs = _extract_segment_refs_from_paragraph(stripped)
            has_tag = bool(seg_refs)

            # Build paragraph ID matching §3.3 convention
            para_id = f"P-{section_id.replace('.', '')}-{idx + 1:03d}"

            provenance_map[para_id] = {
                "section_id": section_id,
                "paragraph_index": idx,
                "source_refs": seg_refs,
                "has_provenance_tag": has_tag,
                "text_hash": _compute_text_hash(stripped),
                "untagged": not has_tag,
            }

    return provenance_map


# ─────────────────────────────────────────────────────────────────────────────
# OD-10: kpi_registry.json generator (lightweight foundation)
# ─────────────────────────────────────────────────────────────────────────────

_NUMERIC_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(tCO2e|GWh|MWh|m³|명|개|년|%|ton|kg|MW|tCO2|℃|ppm|billion|million)"
    r"|(\d[\d,]*(?:\.\d+)?)"
)


def _extract_numeric_claims(body: str) -> list[dict]:
    """
    Extract numeric claims from draft body.
    Returns list of {value, unit, context} dicts.
    """
    claims = []
    for match in _NUMERIC_RE.finditer(body):
        value_str = match.group(1) or match.group(2)
        unit = match.group() if match.group() != value_str else ""
        if value_str:
            try:
                claims.append(
                    {
                        "raw_value": value_str,
                        "normalized_value": float(value_str.replace(",", "")),
                        "unit": unit.strip(),
                        "context": body[max(0, match.start() - 30) : match.end() + 30],
                    }
                )
            except ValueError:
                pass
    return claims


def _infer_data_status(draft_meta: dict, seg_refs: list[str]) -> str:
    """
    Infer data_status from draft metadata.

    - confirmed: fallback_mode=false and has source_tags
    - provisional: fallback_mode=false but no source_tags
    - unresolved: fallback_mode=true
    """
    if draft_meta.get("fallback_mode", False):
        return "unresolved"
    if seg_refs:
        return "confirmed"
    return "provisional"


def _build_kpi_registry(workspace: Path, draft_metas: list[dict]) -> dict:
    """
    Build kpi_registry.json — §2.6/§3.1 OD-10 deliverable.

    Extracts numeric claims from each draft, connects them to source segments,
    and assigns data_status (confirmed/provisional/unresolved).

    This is a *foundation*: actual KPI definitions require LLM enrichment
    and domain expertise that goes beyond what the pipeline can auto-generate.
    """
    project_id = Path(workspace).name
    kpis = []

    for meta in draft_metas:
        section_id = meta.get("section_id", "")
        if not section_id:
            continue

        body = _load_draft_body(workspace, section_id)
        claims = _extract_numeric_claims(body)
        source_tags = meta.get("source_tags", [])

        # Extract segment refs from tags
        seg_refs = []
        for tag in source_tags:
            m = re.search(r"SEG-\d+[@v\d]*", tag)
            if m:
                seg_refs.append(m.group(0))

        data_status = _infer_data_status(meta, seg_refs)

        for i, claim in enumerate(claims[:5]):  # Cap at 5 per section
            kpi_id = f"KPI-{section_id.replace('.', '').upper()}-{i + 1:03d}"
            kpis.append(
                {
                    "kpi_id": kpi_id,
                    "name": claim.get("context", "unnamed metric")[:80],
                    "category": "environmental",  # Default; LLM enrichment would refine this
                    "unit": claim.get("unit") or "N/A",
                    "calculation_method": "auto-extracted from draft",
                    "data_source_type": "estimated",
                    "scope": "Scope 1+2+3",  # Default; would be refined per KPI
                    "reporting_frequency": "annual",
                    "actual_values": [
                        {
                            "year": 2024,  # Placeholder; real implementation would extract year
                            "value": claim.get("normalized_value"),
                            "data_quality": "estimated",
                        }
                    ],
                    "connected_sections": [section_id],
                    "framework_mappings": [],
                    # OD-10 additional fields
                    "data_status": data_status,
                    "source_refs": seg_refs,
                    "paragraph_context": claim.get("context", ""),
                    "raw_value": str(claim.get("raw_value", "")),
                }
            )

    return {
        "registry_version": "1.0",
        "project_id": project_id,
        "kpis": kpis,
    }


def build_context_for_provenance_builder(
    workspace: Path,
    draft_metas: list[dict],
    segment_manifest: dict,
    file_registry: dict,
    internal_review: dict,
    fact_check: dict,
) -> dict:
    """
    provenance-builder 에이전트에 전달할 컨텍스트를 구축한다.
    """
    # SEG 원본 추적 정보 수집
    source_tracking = []
    for meta in draft_metas:
        section_id = meta.get("section_id", "unknown")
        source_tags = meta.get("source_tags", [])

        segment_ids = []
        for tag in source_tags:
            match = re.search(r"SEG-\d+", tag)
            if match:
                segment_ids.append(match.group(0))

        source_tracking.append(
            {
                "section_id": section_id,
                "segment_ids": segment_ids,
                "confidence": meta.get("draft_confidence", 0.0),
                "placeholder_count": meta.get("placeholder_count", 0),
            }
        )

    # CALC 추적 정보
    calc_tracking = []
    for meta in draft_metas:
        section_id = meta.get("section_id", "unknown")
        calc_tags = meta.get("calculation_tags", [])
        for calc_id in calc_tags:
            calc_tracking.append(
                {
                    "section_id": section_id,
                    "calculation_id": calc_id,
                }
            )

    # 파일 혈통 정보
    file_lineage = []
    for entry in file_registry.get("files", []):
        file_id = entry.get("file_id", "unknown")
        converted_path = entry.get("converted_path")
        segment_count = entry.get("segments_count", 0)

        file_lineage.append(
            {
                "file_id": file_id,
                "converted_path": converted_path,
                "segments_count": segment_count,
                "lineage_status": "verified" if segment_count > 0 else "unverified",
            }
        )

    # 검토 결과 요약
    review_summary = {
        "internal_review": {
            "status": "complete" if internal_review else "not_available",
            "sections_reviewed": internal_review.get("summary", {}).get("total_sections_reviewed", 0)
            if internal_review
            else 0,
            "average_confidence": internal_review.get("summary", {}).get("average_confidence", 0.0)
            if internal_review
            else 0.0,
        },
        "fact_check": {
            "status": "complete" if fact_check else "not_available",
            "findings_count": len(fact_check.get("findings", [])) if fact_check else 0,
            "critical_errors": sum(1 for f in fact_check.get("findings", []) if f.get("severity") == "critical")
            if fact_check
            else 0,
        },
    }

    return {
        "workspace": str(workspace),
        "draft_metas_count": len(draft_metas),
        "source_tracking": source_tracking,
        "calc_tracking": calc_tracking,
        "file_lineage": file_lineage,
        "total_files_in_registry": len(file_registry.get("files", [])),
        "total_segments": segment_manifest.get("total_segments", 0),
        "review_summary": review_summary,
        "draft_metas": draft_metas,
        "segment_manifest": segment_manifest,
        "file_registry": file_registry,
    }


def ensure_evidence_pack_dir(workspace: Path) -> Path:
    """10_evidence_pack/ 디렉토리 생성."""
    evidence_dir = workspace / "10_evidence_pack"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    return evidence_dir


def _write_json(path: Path, data: dict) -> None:
    """JSON 파일 쓰기 (pretty-print)."""
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _generate_metadata(
    workspace: Path,
    draft_metas: list[dict],
    segment_manifest: dict,
    file_registry: dict,
    evidence_chain_path: Path,
    fallback_mode: bool = False,
) -> dict:
    """metadata.json 생성. fallback_mode=True이면 폴백 limitation을 명시한다."""
    grounded_count = sum(1 for m in draft_metas if not m.get("fallback_mode", False))
    fallback_count = sum(1 for m in draft_metas if m.get("fallback_mode", False))

    metadata = {
        "pack_id": f"EVPACK-{Path(workspace).name}",
        "workspace_id": str(workspace),
        "created_at": utc_now(),
        "phase": "P7",
        "agent": "provenance-builder",
        "provenance_mode": "fallback" if fallback_mode else "grounded",
        "input_sources": {
            "drafts_count": len(draft_metas),
            "grounded_drafts": grounded_count,
            "fallback_drafts": fallback_count,
            "buckets_count": len(list((workspace / "06_buckets").glob("SEC-*.json")))
            if (workspace / "06_buckets").exists()
            else 0,
            "segments_count": segment_manifest.get("total_segments", 0),
            "normalized_files_count": len(file_registry.get("files", [])),
            "raw_files_count": len([f for f in file_registry.get("files", []) if f.get("source_path")]),
        },
        "evidence_chain_file": str(evidence_chain_path.relative_to(workspace)),
        "audit_trail_complete": not fallback_mode,
        "blocking_issues_found": fallback_count,
        "incomplete_traces": [
            {"section_id": m.get("section_id"), "reason": "fallback mode — evidence 없음"}
            for m in draft_metas
            if m.get("fallback_mode", False)
        ]
        if fallback_mode
        else [],
    }
    return metadata


def _generate_readme(
    workspace: Path,
    draft_metas: list[dict],
    evidence_chain_path: Path,
    metadata_path: Path,
) -> str:
    """readme.md 생성."""
    project_id = Path(workspace).name
    fallback_count = sum(1 for m in draft_metas if m.get("fallback_mode", False))
    evidence_count = sum(1 for m in draft_metas if m.get("source_tags"))

    readme = f"""# 증거 패키지 (Evidence Pack)

## 개요

본 패키지는 `{project_id}` ESG 지속가능경영보고서 초안의 **출처 추적 체인**을 제공한다.

## 생성 정보

- **생성 일시:** {utc_now()}
- **프로젝트:** {project_id}
- **총 섹션 수:** {len(draft_metas)}
- **폴백 모드 섹션:** {fallback_count} (증거 없는 섹션)
- **실제 evidence 섹션:** {evidence_count}

## 폴백 모드 경고

{fallback_count}개 섹션이 폴백 모드로 생성되었습니다. 이는 해당 섹션에 대한 evidence 버킷이 비어있거나
소스 태그가 없어서 LLM이 환각을 생성하지 않도록 placeholder만 삽입된 상태입니다.

다음 섹션에서 evidence 보강이 필요합니다:
"""
    for meta in draft_metas:
        if meta.get("fallback_mode", False):
            section_id = meta.get("section_id", "unknown")
            missing = meta.get("missing_evidence", [])
            reasons = "; ".join([e.get("description", "") for e in missing[:2]])
            readme += f"- **{section_id}**: {reasons or 'evidence 없음'}\n"

    readme += f"""
## 디렉토리 구조

```
10_evidence_pack/
├── readme.md              # 본 파일
├── metadata.json           # 패키지 메타데이터
└── evidence_chain.json     # 출처 추적 체인 (claim-level)
```

## 출처 추적 원칙

| 상태 | 의미 | 처리 |
|------|------|------|
| `src:SEG-NNNN@vN` | 정상 추적 | chain에 등록 |
| `src:CALC-NNNN` | 계산 추적 | 계산 근거 세그먼트 포함 확인 |
| 폴백 모드 섹션 | **추적 불가** | 컨설턴트 확인 필요 |

## 사용 가이드

1. **폴백 모드 섹션 우선 확인**: 위 목록의 섹션부터 evidence를 투입하세요
2. **evidence_chain.json**: 각 섹션의 출처 추적 상세 내역
3. **metadata.json**: 패키지 구성 요소 및 통계
4. **09_handoff/draft_package.json**: 섹션별 confidence 및 placeholder 현황

## 컨설턴트 액션 아이템

- [ ] 폴백 모드 섹션에 대한 원본 자료 투입
- [ ] 각 섹션의 source 태그와 SEG-NNNN 정합성 검증
- [ ] 수치·사실에 대한 고객사 확인
"""
    return readme


def run_provenance_builder(
    workspace: str | Path,
    state_manager=None,
) -> dict:
    """
    P7 증거 체인 구축을 실행한다.

    Args:
        workspace: 워크스페이스 경로

    Returns:
        {
            "success": bool,
            "outputs": list[str],
            "message": str,
            "evidence_chain_path": str,
            "fallback": bool,
        }
    """
    workspace = Path(workspace)
    outputs = []

    # StateManager 초기화
    state_manager = StateManager(workspace)

    # 입력 파일 로드
    draft_metas = load_draft_metas(workspace)
    segment_manifest = load_segment_manifest(workspace)
    file_registry = load_file_registry(workspace)
    internal_review = load_internal_review_report(workspace)
    fact_check = load_fact_check_report(workspace)

    if not draft_metas:
        return {
            "success": False,
            "outputs": [],
            "message": "초안 메타 파일이 없습니다. P4 section-writer를 먼저 실행하세요.",
            "evidence_chain_path": "",
        }

    # 증거 패크 디렉토리 생성
    evidence_dir = ensure_evidence_pack_dir(workspace)
    evidence_chain_path = evidence_dir / "evidence_chain.json"
    metadata_path = evidence_dir / "metadata.json"
    readme_path = evidence_dir / "readme.md"

    # ── 폴백 모드 판정 ─────────────────────────────────────────────────────────
    # 모든 draft가 fallback이면 LLM 호출 없이 폴백 산출물만 생성
    is_fallback = _is_fallback_mode(draft_metas)

    if is_fallback:
        fallback_chain = _generate_fallback_evidence_chain(
            workspace=workspace,
            draft_metas=draft_metas,
            segment_manifest=segment_manifest,
            file_registry=file_registry,
        )
        _write_json(evidence_chain_path, fallback_chain)
        outputs.append(str(evidence_chain_path.relative_to(workspace)))

        metadata = _generate_metadata(
            workspace=workspace,
            draft_metas=draft_metas,
            segment_manifest=segment_manifest,
            file_registry=file_registry,
            evidence_chain_path=evidence_chain_path,
            fallback_mode=True,
        )
        _write_json(metadata_path, metadata)
        outputs.append(str(metadata_path.relative_to(workspace)))

        # OD-10: paragraph_provenance_map.json 생성
        para_map = _build_paragraph_provenance_map(workspace, draft_metas)
        para_map_path = evidence_dir / "paragraph_provenance_map.json"
        _write_json(para_map_path, para_map)
        outputs.append(str(para_map_path.relative_to(workspace)))

        # OD-10: kpi_registry.json 생성
        kpi_registry = _build_kpi_registry(workspace, draft_metas)
        kpi_registry_path = evidence_dir / "kpi_registry.json"
        _write_json(kpi_registry_path, kpi_registry)
        outputs.append(str(kpi_registry_path.relative_to(workspace)))

        readme = _generate_readme(
            workspace=workspace,
            draft_metas=draft_metas,
            evidence_chain_path=evidence_chain_path,
            metadata_path=metadata_path,
        )
        readme_path.write_text(readme, encoding="utf-8")
        outputs.append(str(readme_path.relative_to(workspace)))

        message = f"P7 증거 체인 구축 완료 (폴백): {len(draft_metas)}개 섹션 모두 evidence 없음"

        state_manager.set_phase_status("P7", "complete")
        state_manager.sync()

        log_event(
            event_type="milestone",
            agent="provenance-builder",
            phase="P7",
            message=message,
            workspace=str(workspace),
        )

        return {
            "success": True,
            "outputs": outputs,
            "message": message,
            "evidence_chain_path": str(evidence_chain_path.relative_to(workspace)),
            "fallback": True,
        }

    # ── 정상 경로: LLM으로 provenance-builder 에이전트 호출 ───────────────────
    context = build_context_for_provenance_builder(
        workspace=workspace,
        draft_metas=draft_metas,
        segment_manifest=segment_manifest,
        file_registry=file_registry,
        internal_review=internal_review,
        fact_check=fact_check,
    )

    dispatcher = AgentDispatcher(workspace=workspace, state_manager=state_manager)

    output_files = ["10_evidence_pack/evidence_chain.json"]

    result = dispatcher.dispatch(
        agent="provenance-builder",
        context=context,
        output_files=output_files,
    )

    if result.success and evidence_chain_path.exists():
        outputs.append(str(evidence_chain_path.relative_to(workspace)))

        # 리포트 내용 파싱
        try:
            chain_data = json.loads(evidence_chain_path.read_text(encoding="utf-8"))
            total_sources = len(chain_data.get("source_tracking", []))
            total_calcs = len(chain_data.get("calculation_tracking", []))
            message = f"P7 증거 체인 구축 완료: sources={total_sources}, calculations={total_calcs}"
        except (json.JSONDecodeError, OSError):
            message = "P7 증거 체인 구축 완료 (리포트 파싱 실패)"

        # metadata.json 및 readme.md도 함께 생성
        metadata = _generate_metadata(
            workspace=workspace,
            draft_metas=draft_metas,
            segment_manifest=segment_manifest,
            file_registry=file_registry,
            evidence_chain_path=evidence_chain_path,
            fallback_mode=False,
        )
        _write_json(metadata_path, metadata)
        outputs.append(str(metadata_path.relative_to(workspace)))

        readme = _generate_readme(
            workspace=workspace,
            draft_metas=draft_metas,
            evidence_chain_path=evidence_chain_path,
            metadata_path=metadata_path,
        )
        readme_path.write_text(readme, encoding="utf-8")
        outputs.append(str(readme_path.relative_to(workspace)))

        # OD-10: paragraph_provenance_map.json 생성
        para_map = _build_paragraph_provenance_map(workspace, draft_metas)
        para_map_path = evidence_dir / "paragraph_provenance_map.json"
        _write_json(para_map_path, para_map)
        outputs.append(str(para_map_path.relative_to(workspace)))

        # OD-10: kpi_registry.json 생성
        kpi_registry = _build_kpi_registry(workspace, draft_metas)
        kpi_registry_path = evidence_dir / "kpi_registry.json"
        _write_json(kpi_registry_path, kpi_registry)
        outputs.append(str(kpi_registry_path.relative_to(workspace)))

        state_manager.set_phase_status("P7", "complete")
        state_manager.sync()

        log_event(
            event_type="milestone",
            agent="provenance-builder",
            phase="P7",
            message=message,
            workspace=str(workspace),
        )

        return {
            "success": True,
            "outputs": outputs,
            "message": message,
            "evidence_chain_path": str(evidence_chain_path.relative_to(workspace)),
        }

    else:
        # LLM 실패 시 폴백 증거 체인 생성
        fallback_chain = _generate_fallback_evidence_chain(
            workspace=workspace,
            draft_metas=draft_metas,
            segment_manifest=segment_manifest,
            file_registry=file_registry,
        )
        _write_json(evidence_chain_path, fallback_chain)
        outputs.append(str(evidence_chain_path.relative_to(workspace)))

        metadata = _generate_metadata(
            workspace=workspace,
            draft_metas=draft_metas,
            segment_manifest=segment_manifest,
            file_registry=file_registry,
            evidence_chain_path=evidence_chain_path,
            fallback_mode=True,
        )
        _write_json(metadata_path, metadata)
        outputs.append(str(metadata_path.relative_to(workspace)))

        readme = _generate_readme(
            workspace=workspace,
            draft_metas=draft_metas,
            evidence_chain_path=evidence_chain_path,
            metadata_path=metadata_path,
        )
        readme_path.write_text(readme, encoding="utf-8")
        outputs.append(str(readme_path.relative_to(workspace)))

        # OD-10: paragraph_provenance_map.json 생성
        para_map = _build_paragraph_provenance_map(workspace, draft_metas)
        para_map_path = evidence_dir / "paragraph_provenance_map.json"
        _write_json(para_map_path, para_map)
        outputs.append(str(para_map_path.relative_to(workspace)))

        # OD-10: kpi_registry.json 생성
        kpi_registry = _build_kpi_registry(workspace, draft_metas)
        kpi_registry_path = evidence_dir / "kpi_registry.json"
        _write_json(kpi_registry_path, kpi_registry)
        outputs.append(str(kpi_registry_path.relative_to(workspace)))

        return {
            "success": True,
            "outputs": outputs,
            "message": "P7 증거 체인 구축 완료 (폴백): provenance-builder 호출 실패",
            "evidence_chain_path": str(evidence_chain_path.relative_to(workspace)),
            "fallback": True,
        }


def _generate_fallback_evidence_chain(
    workspace: Path,
    draft_metas: list[dict],
    segment_manifest: dict,
    file_registry: dict,
) -> dict:
    """provenance-builder 호출 실패 또는 폴백 모드 시 폴백 증거 체인 생성."""
    source_tracking = []
    for meta in draft_metas:
        section_id = meta.get("section_id", "unknown")
        source_tags = meta.get("source_tags", [])

        segment_refs = []
        for tag in source_tags:
            match = re.search(r"SEG-\d+", tag)
            if match:
                segment_refs.append(match.group(0))

        source_tracking.append(
            {
                "section_id": section_id,
                "segment_refs": segment_refs,
                "provenance_status": "unverified",
                "confidence": meta.get("draft_confidence", 0.0),
                "fallback_mode": meta.get("fallback_mode", False),
            }
        )

    file_lineage = []
    for entry in file_registry.get("files", []):
        file_lineage.append(
            {
                "file_id": entry.get("file_id", "unknown"),
                "source_path": entry.get("source_path"),
                "converted_path": entry.get("converted_path"),
                "segments_count": entry.get("segments_count", 0),
                "lineage_status": "unverified",
            }
        )

    return {
        "evidence_chain_version": "1.0",
        "generated_at": utc_now(),
        "workspace": str(workspace),
        "source": "fallback_generated",
        "note": "모든 섹션이 폴백 모드이거나 provenance-builder 호출 실패로 자동 생성된 폴백 증거 체인",
        "source_tracking": source_tracking,
        "calculation_tracking": [],
        "file_lineage": file_lineage,
        "total_sections": len(draft_metas),
        "total_segments": segment_manifest.get("total_segments", 0),
        "total_files": len(file_registry.get("files", [])),
        "provenance_complete": False,
        "gaps": [
            "CALC 추적 정보 없음",
            "증거 연속성 검증 미실시",
            "원본 파일 아카이브 미포함",
        ],
        "recommendations": [
            "원본 파일을 10_evidence_pack/에 아카이브하세요",
            "CALC-NNNN 계산 추적을 수동으로 확인하세요",
            "증거 연속성 단절 지점을 수동 검증하세요",
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
    """P7 증거 체인 구축 스크립트."""
    print(f"[run_provenance_builder] P7 증거 체인 구축 시작")
    print(f"  workspace: {workspace}")

    result = run_provenance_builder(workspace=workspace)

    print()
    if result["success"]:
        print(f"{'⚠️ ' if result.get('fallback') else '✅'} {result['message']}")
        print(f"   Evidence chain: {result['evidence_chain_path']}")
        print(f"   Outputs: {result.get('outputs', [])}")
        return 0
    else:
        print(f"❌ {result['message']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
