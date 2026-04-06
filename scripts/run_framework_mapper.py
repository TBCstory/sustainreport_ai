#!/usr/bin/env python3.13
"""
run_framework_mapper.py — P3 버킷 구축 스크립트

역할:
1. toc-planner 출력 (structure_index, segment_manifest) 읽기
2. structure_index.framework_mappings를 기반으로 버킷 직접 구축
3. framework-mapper LLM은 enrichment 전용 (필수 아님)
4. 06_buckets/SEC-*.json + framework_index.json 생성

사용법:
    from scripts.run_framework_mapper import run_framework_mapper
    result = run_framework_mapper("/path/to/PRJ-YYYY-CODE-NNN")
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


def load_structure_index(workspace: Path) -> dict:
    """structure_index.json 로드."""
    path = workspace / "05_planning" / "structure_index.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_segment_manifest(workspace: Path) -> dict:
    """segment_manifest.json 로드."""
    path = workspace / "04_segments" / "segment_manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_framework_db(templates_dir: Path) -> dict:
    """프레임워크별 공시 항목 DB 로드."""
    db_path = templates_dir / "framework_db"
    frameworks = {}

    if not db_path.is_dir():
        return frameworks

    for db_file in db_path.glob("*_db.json"):
        try:
            name = db_file.stem.replace("_db", "")
            data = json.loads(db_file.read_text(encoding="utf-8"))
            frameworks[name] = data
        except (json.JSONDecodeError, OSError):
            continue

    return frameworks


def ensure_buckets_dir(workspace: Path) -> Path:
    """06_buckets 디렉토리 생성."""
    buckets_dir = workspace / "06_buckets"
    buckets_dir.mkdir(parents=True, exist_ok=True)
    return buckets_dir


def save_bucket(section_id: str, bucket_data: dict, workspace: Path) -> Path:
    """섹션 버킷 파일 저장."""
    buckets_dir = ensure_buckets_dir(workspace)
    bucket_path = buckets_dir / f"{section_id}.json"

    # 메타 정보 추가
    bucket_data["section_id"] = section_id
    bucket_data["bucket_path"] = str(bucket_path.relative_to(workspace))
    bucket_data["generated_at"] = utc_now()

    bucket_path.write_text(
        json.dumps(bucket_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return bucket_path


def _extract_body(seg_path: Path) -> str:
    """세그먼트 파일에서 YAML front matter를 제외한 본문을 추출한다."""
    text = seg_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3 :].strip()
    return text.strip()


def _load_segment_content(workspace: Path, seg_entry: dict) -> str:
    """세그먼트 본문을 로드한다. 여러 경로를 순서대로 시도."""
    # 1) file_path 필드 (HD-2에서 추가된 필드)
    fp = seg_entry.get("file_path")
    if fp:
        full = workspace / fp
        if full.exists():
            return _extract_body(full)

    # 2) 직접 경로 fallback
    seg_id = seg_entry.get("segment_id", "")
    direct = workspace / "04_segments" / f"{seg_id}.md"
    if direct.exists():
        return _extract_body(direct)

    # 3) content_preview fallback
    preview = seg_entry.get("content_preview", "")
    if preview:
        return preview

    return ""


def _build_buckets_from_structure_index(
    workspace: Path,
    target_sections: list[dict],
    segment_manifest: dict,
    framework_db: dict,
) -> int:
    """
    structure_index.framework_mappings를 기반으로 버킷을 결정론적으로 구축한다.
    LLM 의존 없이 structure_index + segment_manifest만으로 버킷을 생성하므로
    generated_fallback 상태를 방지한다.

    Returns:
        생성된 버킷 수
    """
    buckets_dir = ensure_buckets_dir(workspace)
    segments = segment_manifest.get("segments", [])

    # 섹션별 세그먼트 매칭 및 라우팅 메타데이터 생성
    def _find_segments_for_section(section: dict) -> list[dict]:
        """해당 섹션에 매칭되는 세그먼트를 찾고 라우팅 메타데이터를 생성한다."""
        toc_path = section.get("toc_path", [])
        heading_text = section.get("heading_text", "")
        section_id = section.get("section_id", "")
        mappings = section.get("framework_mappings", [])

        # toc_path 키워드 정규화 (heading_path가 문자열인 경우 리스트로)
        toc_keywords = []
        for p in toc_path:
            if isinstance(p, str) and p:
                toc_keywords.append(p.lower().strip())
            elif isinstance(p, (list, tuple)) and p:
                toc_keywords.extend([str(x).lower().strip() for x in p if x])

        matched = []
        for seg in segments:
            seg_id = seg.get("segment_id", "")
            # heading_path는 문자열 (예: "지속가능경영 개요") 또는 None
            seg_heading = seg.get("heading_path") or ""
            seg_file_path = seg.get("file_path", "")

            # 실제 세그먼트 파일에서 content 읽기
            # HD-2: _load_segment_content 헬퍼 사용
            seg_content = _load_segment_content(workspace, seg)

            seg_content_lower = seg_content.lower()
            seg_heading_lower = seg_heading.lower() if isinstance(seg_heading, str) else ""

            routing_reason = None
            confidence = 0.0
            evidence_unit_type = "text"
            evidence_binding_mode = "reference_only"

            # HD-2: keyword matching 강화 — blueprint 키워드 추가
            all_keywords = list(toc_keywords)
            # blueprint에서 추가 키워드 추출 (section에서 직접 가져옴)
            bp_keywords = []
            section_blueprint = section.get("blueprint", {})
            if section_blueprint:
                bp_keywords.extend(section_blueprint.get("required_subsections", []))
                bp_keywords.extend(section_blueprint.get("framework_disclosures", []))
            all_keywords.extend([kw.lower().strip() for kw in bp_keywords if kw])

            # 매칭 로직
            matched_reason = False
            match_type = None

            # 1. toc_path 전체 또는 일부 키워드가 세그먼트 heading/content에 포함
            match_count = 0
            if all_keywords:
                heading_match = any(kw in seg_heading_lower for kw in all_keywords)
                content_match = any(kw in seg_content_lower for kw in all_keywords)
                # HD-2: 매칭된 키워드 수 카운트
                match_count = sum(1 for kw in all_keywords if kw in seg_content_lower or kw in seg_heading_lower)

                if heading_match or content_match:
                    matched_reason = True
                    if heading_match and content_match:
                        match_type = "heading_and_content"
                    elif heading_match:
                        match_type = "heading_only"
                    else:
                        match_type = "content_only"

            # 2. section_id 기반 자동 포함 (부모 섹션에 하위 세그먼트 포함)
            if not matched_reason and section_id.startswith("SEC-"):
                # section_id가 세그먼트 heading에 포함되면 매칭
                # 예: SEC-3.1 → "3.1" 또는 "SEC-3.1"이 heading에 포함
                sec_num_match = section_id.replace("SEC-", "")
                if sec_num_match in seg_heading_lower or section_id.lower() in seg_heading_lower:
                    matched_reason = True
                    match_type = "section_id_match"

            # 수치/핵심 데이터 감지
            numeric_patterns = ["tco2e", "gwh", "m³", "명", "개", "년", "%", "ton", "kg", "mw"]
            if any(p in seg_content_lower for p in numeric_patterns):
                evidence_unit_type = "numeric"
                evidence_binding_mode = "inline_citation"

            # HD-2: keyword 매칭 보너스 (match_count >= 2 이상 시)
            confidence_bonus = 0.0
            if match_count >= 3:
                confidence_bonus = 0.15
            elif match_count >= 2:
                confidence_bonus = 0.1

            # 프레임워크 매핑 기반 confidence
            if matched_reason and mappings:
                weight_map = {"primary": 0.9, "secondary": 0.6, "partial": 0.4}
                confidence = sum(weight_map.get(m.get("coverage_type", "secondary"), 0.5) for m in mappings) / len(
                    mappings
                )
                confidence += confidence_bonus
            elif matched_reason:
                confidence = 0.5 + confidence_bonus

            if matched_reason:
                routing_reason = f"{match_type}"
                if mappings:
                    fw_names = [m.get("framework", "") for m in mappings]
                    routing_reason += f" + framework:{','.join(fw_names)}"

                matched.append(
                    {
                        "segment_id": seg_id,
                        "source_file_id": seg.get("source_file_id"),
                        "heading_path": seg.get("heading_path"),
                        "routing_reason": routing_reason,
                        "confidence_score": round(confidence, 3),
                        "evidence_unit_type": evidence_unit_type,
                        "evidence_binding_mode": evidence_binding_mode,
                    }
                )

        return matched

    buckets_created = 0
    for section in target_sections:
        section_id = section.get("section_id", "")
        if not section_id or not section_id.startswith("SEC-"):
            continue

        mappings = section.get("framework_mappings", [])
        matched_segments = _find_segments_for_section(section)

        # confidence: matched_segments 기반 (routing_reason이 있으면 grounded)
        has_grounded = any("routing_reason" in seg for seg in matched_segments)
        if not matched_segments:
            confidence = 0.0
            bucket_status_type = "empty"
        elif has_grounded:
            confidence = sum(seg.get("confidence_score", 0.5) for seg in matched_segments) / len(matched_segments)
            bucket_status_type = "grounded"
        else:
            confidence = 0.0
            bucket_status_type = "fallback"

        # LLM enrichment가 아니면 status="derived", 실패 시만 "generated_fallback"
        bucket_data = {
            "section_id": section_id,
            "heading_text": section.get("heading_text", ""),
            "bucket_path": f"06_buckets/{section_id}.json",
            "generated_at": utc_now(),
            "status": "derived",
            "bucket_status_type": bucket_status_type,
            "mappings": mappings,
            "segments": matched_segments,
            "confidence": round(confidence, 3),
            "note": "structure_index.framework_mappings 기반 결정론적 생성",
        }

        bucket_path = buckets_dir / f"{section_id}.json"
        bucket_path.write_text(
            json.dumps(bucket_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        buckets_created += 1

    return buckets_created


def build_context_for_framework_mapper(
    workspace: Path,
    structure_index: dict,
    segment_manifest: dict,
    framework_db: dict,
) -> dict:
    """
    framework-mapper 에이전트에 전달할 컨텍스트를 구축한다.
    """
    # structure_index에서 섹션 목록 추출
    sections = structure_index.get("entries", [])

    # segment_manifest에서 세그먼트 목록 추출
    segments = segment_manifest.get("segments", [])

    # 프레임워크 목록
    frameworks = list(framework_db.keys())

    return {
        "workspace": str(workspace),
        "sections_count": len(sections),
        "segments_count": len(segments),
        "frameworks": frameworks,
        "section_ids": [s.get("section_id") for s in sections if s.get("section_id", "").startswith("SEC-")],
        "structure_index": structure_index,
        "segment_manifest": segment_manifest,
        "framework_db": framework_db,
    }


def run_framework_mapper(
    workspace: str | Path,
    section_ids: Optional[list[str]] = None,
) -> dict:
    """
    framework-mapper를 실행하여 P3 버킷을 구축한다.

    Args:
        workspace: 워크스페이스 경로
        section_ids: 특정 섹션만 처리할 경우 (None이면 전체)

    Returns:
        {"success": bool, "outputs": list[str], "message": str, "buckets_created": int}
    """
    workspace = Path(workspace)
    outputs = []

    # StateManager 초기화
    state_manager = StateManager(workspace)

    # 상태 파일 로드
    structure_index = load_structure_index(workspace)
    segment_manifest = load_segment_manifest(workspace)
    templates_dir = PROJECT_ROOT / "templates"
    framework_db = load_framework_db(templates_dir)

    if not structure_index:
        return {
            "success": False,
            "outputs": [],
            "message": "structure_index.json이 없습니다. P2 toc-planner를 먼저 실행하세요.",
            "buckets_created": 0,
        }

    # 섹션 목록
    all_sections = structure_index.get("entries", [])
    target_sections = all_sections

    if section_ids:
        section_id_set = set(section_ids)
        target_sections = [s for s in all_sections if s.get("section_id") in section_id_set]

    if not target_sections:
        return {
            "success": False,
            "outputs": [],
            "message": f"처리할 섹션이 없습니다. section_ids={section_ids}",
            "buckets_created": 0,
        }

    # framework-mapper 에이전트 호출
    context = build_context_for_framework_mapper(
        workspace=workspace,
        structure_index=structure_index,
        segment_manifest=segment_manifest,
        framework_db=framework_db,
    )
    context["target_section_ids"] = [s.get("section_id") for s in target_sections]

    # Dispatcher 초기화
    dispatcher = AgentDispatcher(workspace=workspace, state_manager=state_manager)

    # framework-mapper는 ephemeral → 단일 호출로 전체 처리
    result = dispatcher.dispatch(
        agent="framework-mapper",
        context=context,
        output_files=[],  # 출력은 직접 파일로 기록
    )

    if not result.success:
        # 실패 시에도 framework_index.json이 없으면 수동 생성 시도
        _generate_fallback_framework_index(workspace, target_sections, framework_db)
        return {
            "success": False,
            "outputs": outputs,
            "message": f"framework-mapper 호출 실패: {result.error}",
            "buckets_created": 0,
        }

    # ─── 결정론적 버킷 구축 (LLM 의존 제거) ───────────────────────────────────
    # structure_index.framework_mappings + segment_manifest로 직접 버킷 생성
    # LLM은 enrichment 전용으로, 버킷 생성 실패 시만 fallback으로 사용
    buckets_created = _build_buckets_from_structure_index(
        workspace=workspace,
        target_sections=target_sections,
        segment_manifest=segment_manifest,
        framework_db=framework_db,
    )

    # LLM 결과를 enrichment로 활용 시도 (버킷 상태 upgrade만)
    if result.success and result.content:
        _enrich_buckets_from_llm_result(workspace, target_sections, result.content)

    # 버킷이 생성되었으면 outputs 갱신
    if buckets_created > 0:
        outputs = [str(p.relative_to(workspace)) for p in ensure_buckets_dir(workspace).glob("SEC-*.json")]
    else:
        # _build_buckets_from_structure_index가 0이면 (절대 발생 안 해야 함)
        _generate_fallback_buckets(workspace, target_sections)
        outputs = [str(p.relative_to(workspace)) for p in ensure_buckets_dir(workspace).glob("SEC-*.json")]
        buckets_created = len(outputs)

    # framework_index.json 생성
    framework_index = _build_framework_index(workspace, framework_db)
    framework_index_path = workspace / "05_planning" / "framework_index.json"
    framework_index_path.write_text(
        json.dumps(framework_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    outputs.append(str(framework_index_path.relative_to(workspace)))

    # 상태 갱신
    state_manager.sync()

    # 로그 이벤트
    log_event(
        event_type="milestone",
        agent="framework-mapper",
        phase="P3",
        message=f"버킷 구축 완료: {buckets_created}개 버킷 생성, framework_index 갱신",
        workspace=str(workspace),
    )

    return {
        "success": True,
        "outputs": outputs,
        "message": f"P3 버킷 구축 완료: {buckets_created}개 버킷",
        "buckets_created": buckets_created,
    }


def _enrich_buckets_from_llm_result(
    workspace: Path,
    target_sections: list[dict],
    content: str,
) -> None:
    """
    LLM 결과를 사용하여 기존 derived 버킷을 enrichment한다.
    LLM이 반환한 coverage_gaps, 추가 mappings 등을 버킷에 병합한다.
    LLM 결과 파싱 실패 시 아무 것도 하지 않는다 (버킷은 이미 derived 상태).
    """
    import re

    try:
        # JSON 블록 추출
        json_blocks = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
        if not json_blocks:
            return

        for block in json_blocks:
            try:
                llm_data = json.loads(block)
                section_id = llm_data.get("section_id")
                if not section_id or not section_id.startswith("SEC-"):
                    continue

                bucket_path = workspace / "06_buckets" / f"{section_id}.json"
                if not bucket_path.exists():
                    continue

                existing = json.loads(bucket_path.read_text(encoding="utf-8"))

                # enrichment: LLM이 더 정확한 mappings/coverage_gaps를 제공하면 upgrade
                if "mappings" in llm_data and llm_data["mappings"]:
                    existing["mappings"] = llm_data["mappings"]
                if "coverage_gaps" in llm_data:
                    existing["coverage_gaps"] = llm_data["coverage_gaps"]
                if "segments" in llm_data and llm_data["segments"]:
                    existing["segments"] = llm_data["segments"]

                # confidence upgrade (LLM enrichment 후)
                if "confidence" in llm_data and isinstance(llm_data["confidence"], (int, float)):
                    existing["confidence"] = round(float(llm_data["confidence"]), 3)

                existing["status"] = "enriched"
                existing["note"] = "LLM enrichment 완료"

                bucket_path.write_text(
                    json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except (json.JSONDecodeError, OSError):
                continue
    except Exception:
        # LLM enrichment 실패는 치명적이지 않음 — 버킷은 이미 derived 상태
        pass


def _generate_fallback_buckets(workspace: Path, sections: list[dict]) -> None:
    """버킷 생성 실패 시 폴백: 빈 버킷 생성."""
    buckets_dir = ensure_buckets_dir(workspace)

    for section in sections:
        section_id = section.get("section_id")
        if not section_id or not section_id.startswith("SEC-"):
            continue

        bucket_data = {
            "section_id": section_id,
            "heading_text": section.get("heading_text", ""),
            "bucket_path": f"06_buckets/{section_id}.json",
            "generated_at": utc_now(),
            "status": "generated_fallback",
            "mappings": [],
            "segments": [],
            "confidence": 0.0,
            "note": "structure_index.framework_mappings 기반 결정론적 생성 실패",
        }

        bucket_path = buckets_dir / f"{section_id}.json"
        bucket_path.write_text(
            json.dumps(bucket_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _generate_fallback_framework_index(
    workspace: Path,
    sections: list[dict],
    framework_db: dict,
) -> dict:
    """framework_index.json 폴백 생성."""
    return _build_framework_index(workspace, framework_db)


def _build_framework_index(workspace: Path, framework_db: dict) -> dict:
    """framework_index.json 생성."""
    buckets_dir = workspace / "06_buckets"

    section_mappings: dict[str, list[dict]] = {}
    for bucket_file in buckets_dir.glob("SEC-*.json"):
        try:
            data = json.loads(bucket_file.read_text(encoding="utf-8"))
            section_id = data.get("section_id")
            if section_id:
                section_mappings[section_id] = data.get("mappings", [])
        except (json.JSONDecodeError, OSError):
            continue

    return {
        "framework_index_version": "1.0",
        "generated_at": utc_now(),
        "frameworks": list(framework_db.keys()),
        "section_mappings": section_mappings,
        "total_mappings": sum(len(m) for m in section_mappings.values()),
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
    help="특정 섹션만 처리 (SEC-X.Y.Z)",
)
def main(workspace: Path, section_ids: tuple[str, ...]) -> int:
    """P3 버킷 구축 스크립트."""
    print(f"[run_framework_mapper] P3 버킷 구축 시작")
    print(f"  workspace: {workspace}")
    if section_ids:
        print(f"  sections: {list(section_ids)}")
    else:
        print(f"  sections: all")

    result = run_framework_mapper(
        workspace=workspace,
        section_ids=list(section_ids) if section_ids else None,
    )

    print()
    if result["success"]:
        print(f"✅ {result['message']}")
        print(f"   Buckets created: {result['buckets_created']}")
        print(f"   Outputs: {result['outputs']}")
        return 0
    else:
        print(f"❌ {result['message']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
