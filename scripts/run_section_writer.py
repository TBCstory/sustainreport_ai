#!/usr/bin/env python3.13
"""
run_section_writer.py — P4 초안 작성 스크립트

역할:
1. framework_mapper 출력 (버킷) 읽기
2. section-writer 에이전트 호출 (섹션별 병렬 가능)
3. 07_drafts/SEC-*.md + SEC-*_meta.json 생성
4. placeholder → draft_queries.json 등록 (중복 방지)
5. manual 섹션은 자동 draft에서 제외

사용법:
    from scripts.run_section_writer import run_section_writer
    result = run_section_writer(
        workspace="/path/to/PRJ-YYYY-CODE-NNN",
        section_ids=["SEC-3.1", "SEC-3.2"],
        parallel=True,
    )
"""

from __future__ import annotations

import json
import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
import yaml
from filelock import FileLock

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.dispatch_agent import AgentDispatcher
from scripts.log_event import log_event
from scripts.state_manager import StateManager

# ─────────────────────────────────────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────────────────────────────────────


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _para_num(text: str, pos: int) -> int:
    """1-based paragraph number at byte position."""
    return text[:pos].count("\n\n") + 1


def load_buckets(workspace: Path) -> dict[str, dict]:
    """06_buckets/에서 모든 버킷 로드."""
    buckets_dir = workspace / "06_buckets"
    if not buckets_dir.is_dir():
        return {}

    buckets = {}
    for bucket_file in sorted(buckets_dir.glob("SEC-*.json")):
        try:
            data = json.loads(bucket_file.read_text(encoding="utf-8"))
            section_id = data.get("section_id", bucket_file.stem)
            buckets[section_id] = data
        except (json.JSONDecodeError, OSError):
            continue

    return buckets


def load_writing_blueprint(workspace: Path) -> dict:
    """writing_blueprint.json 로드."""
    path = workspace / "05_planning" / "writing_blueprint.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_structure_index(workspace: Path) -> dict:
    """structure_index.json 로드."""
    path = workspace / "05_planning" / "structure_index.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_section_manifest(workspace: Path) -> dict:
    """section_manifest.json 로드. 없으면 빈 구조 반환."""
    path = workspace / "05_planning" / "section_manifest.json"
    if not path.exists():
        return {"sections": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"sections": []}


def is_manual_section(section_id: str, manifest: dict) -> bool:
    """section_manifest에서 manual 섹션 여부를 확인."""
    for entry in manifest.get("sections", []):
        if entry.get("section_id") == section_id and entry.get("writing_mode") == "manual":
            return True
    return False


def normalize_blueprint_sections(blueprint: dict | list | None) -> dict[str, dict]:
    """
    writing_blueprint의 sections를 section_id -> spec 맵으로 정규화한다.

    지원 shape:
    - {"sections": [{...}, {...}]}
    - {"sections": {"SEC-3.1": {...}}}
    - [{...}, {...}]
    """
    raw_sections = blueprint.get("sections", {}) if isinstance(blueprint, dict) else blueprint
    normalized: dict[str, dict] = {}

    if isinstance(raw_sections, list):
        for section in raw_sections:
            if not isinstance(section, dict):
                continue
            section_id = section.get("section_id")
            if section_id:
                normalized[section_id] = section
        return normalized

    if isinstance(raw_sections, dict):
        for raw_key, section in raw_sections.items():
            if not isinstance(section, dict):
                continue
            section_id = section.get("section_id") or str(raw_key).replace("\\.", ".")
            normalized[section_id] = section

    return normalized


def load_style_guide() -> dict:
    """style_guide.json 로드."""
    path = PROJECT_ROOT / "guidance" / "style_guide.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_terminology_dictionary() -> dict:
    """terminology_dictionary.json 로드."""
    path = PROJECT_ROOT / "guidance" / "terminology_dictionary.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def ensure_drafts_dir(workspace: Path) -> Path:
    """07_drafts/ 디렉토리 생성."""
    drafts_dir = workspace / "07_drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    return drafts_dir


def _para_num(text: str, pos: int) -> int:
    """text 내 position之前的段落数 (1부터 시작)."""
    return text[:pos].count("\n\n") + 1


def save_draft_meta(
    section_id: str,
    meta: dict,
    workspace: Path,
) -> Path:
    """초안 메타 JSON 저장."""
    drafts_dir = ensure_drafts_dir(workspace)
    meta_path = drafts_dir / f"{section_id}_meta.json"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return meta_path


def save_draft(section_id: str, content: str, workspace: Path) -> Path:
    """초안 Markdown 저장."""
    drafts_dir = ensure_drafts_dir(workspace)
    draft_path = drafts_dir / f"{section_id}.md"
    draft_path.write_text(content, encoding="utf-8")
    return draft_path


# ─────────────────────────────────────────────────────────────────────────────
# Draft Queries 관리
# ─────────────────────────────────────────────────────────────────────────────


def load_draft_queries(workspace: Path) -> dict:
    """draft_queries.json 로드. 없으면 기본 구조 반환."""
    path = workspace / "draft_queries.json"
    if not path.exists():
        return {
            "query_version": "1.0",
            "project_id": workspace.name,
            "queries": [],
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "query_version": "1.0",
            "project_id": workspace.name,
            "queries": [],
        }


def save_draft_queries(workspace: Path, data: dict) -> None:
    """draft_queries.json 저장."""
    path = workspace / "draft_queries.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _locked_draft_queries_update(
    workspace: Path,
    section_id: str,
    new_queries: list[dict],
) -> list[str]:
    """Thread-safe wrapper around update_draft_queries using FileLock.

    Prevents race conditions during parallel section drafting where multiple
    threads might read-modify-write draft_queries.json simultaneously.
    """
    dq_path = workspace / "draft_queries.json"
    lock_path = workspace / ".draft_queries.lock"
    with FileLock(str(lock_path), timeout=30):
        return _update_draft_queries_impl(workspace, section_id, new_queries)


def _update_draft_queries_impl(
    workspace: Path,
    section_id: str,
    new_queries: list[dict],
) -> list[str]:
    """Internal implementation: new queries를 기존 draft_queries.json에 병합.

    - 중복 (section_id + question)인 기존 query는 건드리지 않음
    - 새 query는 DQ-NNN ID 발급 후 추가
    - resolved 상태인 기존 query는 open으로 되돌리지 않음

    Returns:
        list of newly added query_ids
    """
    data = load_draft_queries(workspace)
    existing = data.get("queries", [])

    added_ids = []
    for nq in new_queries:
        existing_match = _is_duplicate_query(existing, nq)
        if existing_match is not None:
            # 중복이지만 resolved 상태이면 open으로 되돌림
            if existing_match.get("status") == "resolved":
                existing_match["status"] = "open"
                existing_match["raised_at"] = utc_now()
            continue

        # 새 query 추가
        query_id = _next_dq_id(existing + [{"query_id": i} for i in added_ids])
        new_entry = {
            "query_id": query_id,
            "section_id": nq.get("section_id", section_id),
            "question": nq.get("question", ""),
            "status": nq.get("status", "open"),
            "priority": nq.get("priority", "medium"),
            "raised_by": nq.get("raised_by", "section-writer"),
            "raised_at": nq.get("raised_at", utc_now()),
        }
        existing.append(new_entry)
        added_ids.append(query_id)

    data["queries"] = existing
    data["query_version"] = data.get("query_version", "1.0")
    data["project_id"] = workspace.name

    save_draft_queries(workspace, data)
    return added_ids


# ─────────────────────────────────────────────────────────────────────────────
# HD-5: Draft Query Typed Fields
# ─────────────────────────────────────────────────────────────────────────────


def _infer_query_type(question: str) -> str:
    """placeholder 텍스트에서 query_type을 추론한다.

    5종: data_confirmation, additional_data_request,
         numeric_discrepancy, policy_clarification, scope_question
    """
    q_lower = question.lower()

    # 수치 불일치 키워드
    if any(kw in q_lower for kw in ["불일치", "차이", "다른 수치", "discrepancy", "mismatch"]):
        return "numeric_discrepancy"

    # 추가 자료 요청 키워드 ("추가" 단독, "미확보/누락/없습니다/부족/미제출" + "필요" 조합)
    if "추가" in q_lower or any(kw in q_lower for kw in ["미확보", "누락", "없습니다", "부족", "미제출"]):
        return "additional_data_request"

    # 범위/경계 키워드
    if any(kw in q_lower for kw in ["범위", "경계", "scope", "boundary", "포함 여부"]):
        return "scope_question"

    # 정책/제도 키워드
    if any(kw in q_lower for kw in ["정책", "제도", "절차", "규정", "방침", "policy"]):
        return "policy_clarification"

    # 기본값: 데이터 확인
    return "data_confirmation"


def _extract_query_context(body: str, placeholder_text: str) -> str:
    """placeholder 주변 문맥 (앞뒤 1문장)을 추출한다."""
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if placeholder_text in line:
            context_lines = []
            if i > 0:
                context_lines.append(lines[i - 1].strip())
            context_lines.append(line.strip())
            if i < len(lines) - 1:
                context_lines.append(lines[i + 1].strip())
            return " ".join(context_lines)[:300]
    return ""


def _get_related_segments(bucket_data: Optional[dict]) -> list[str]:
    """bucket에서 관련 segment ID 목록을 추출한다."""
    if not bucket_data:
        return []
    segments = bucket_data.get("segments", [])
    return [s.get("segment_id", "") for s in segments if s.get("segment_id")]


# ─────────────────────────────────────────────────────────────────────────────
# Draft Query Extraction
# ─────────────────────────────────────────────────────────────────────────────


def _extract_draft_queries_from_content(
    content: str,
    section_id: str,
    bucket_data: Optional[dict] = None,
) -> list[dict]:
    """
    초안 본문에서 [확인필요: ...] placeholder를 추출하여
    draft query 형태로 변환한다.

    Returns:
        list of DraftQuery dicts (query_id 제외)
    """
    pattern = re.compile(r"\[확인필요[:\s]+([^\]]+)\]")
    queries = []
    for match in pattern.finditer(content):
        question_text = match.group(1).strip()
        if question_text:
            queries.append(
                {
                    "query_type": _infer_query_type(question_text),
                    "section_id": section_id,
                    "question": question_text,
                    "context": _extract_query_context(content, match.group(0)),
                    "related_segments": _get_related_segments(bucket_data),
                    "status": "open",
                    "priority": _infer_priority(question_text),
                    "raised_by": "section-writer",
                    "raised_at": utc_now(),
                }
            )
    return queries


# ─────────────────────────────────────────────────────────────────────────────
# OD-9: Source Tag Enforcement
# 설계: purrfect-riding-blossom.md §2.5 Writer Agents ("모든 문장에 태그 필수")
#       §5 할루시네이션 방지 ("provenance 태그 없는 문장 자동 플래그")
# ─────────────────────────────────────────────────────────────────────────────

PROVENANCE_TAG_PATTERN = re.compile(r"<!--\s*src:SEG-\d+[@v\d]*\s*-->|<!--\s*src:CALC-\d+\s*-->", re.IGNORECASE)
PARAGRAPH_SPLITTER = re.compile(r"\n\n+")


# Markdown header line pattern (## až ##)
_MARKDOWN_HEADER_RE = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)


def _find_untagged_sentences(body: str) -> list[dict]:
    """
    초안 본문에서 provenance 태그가 없는 문단을 찾는다.

    문단 내 모든 문장이 태그로 시작하거나 포함되어야 한다.
    태그 없는 문단을 {"para_index", "text", "start_offset"}로 반환.

    Returns:
        list of untagged paragraph dicts
    """
    untagged = []
    paragraphs = PARAGRAPH_SPLITTER.split(body)

    offset = 0
    for idx, para in enumerate(paragraphs):
        # 빈 문단 스킵
        stripped = para.strip()
        if not stripped:
            offset += len(para) + 2  # split delimiter
            continue

        # §2.5 설계: 모든 문장에 <!-- src:SEG-XXXXX --> 또는 <!-- src:CALC-XXXX --> 태그 필수
        # HTML comment 제거 시 src/provenance 태그는 보존하고 anchor 태그만 제거
        # anchor 태그: <!-- anchor:SEC-3.1 --> — provenance evidence가 아님
        content_for_check = re.sub(r"<!--\s*anchor:[^\s]+\s*-->", "", stripped)
        content_for_check = re.sub(r"^---$", "", content_for_check, flags=re.MULTILINE)

        # 헤더만으로 구성된 문단 (§heading)은 provenance 태그 불필요 — 스킵
        header_lines = [ln.strip() for ln in content_for_check.splitlines() if ln.strip()]
        if header_lines and all(_MARKDOWN_HEADER_RE.match(ln) for ln in header_lines):
            offset += len(para) + 2
            continue

        # 태그가 없는 문단 감지
        if not PROVENANCE_TAG_PATTERN.search(content_for_check):
            untagged.append(
                {
                    "para_index": idx,
                    "text": stripped[:200],  # 처음 200자만
                    "start_offset": offset,
                }
            )

        offset += len(para) + 2

    return untagged


def _register_source_tag_violations(
    workspace: Path,
    section_id: str,
    untagged: list[dict],
    bucket_data: dict,
) -> list[str]:
    """
    provenance 태그 없는 문단을 draft_queries.json에 DQ-*로 등록한다.

    OD-9 enforcement: 설계 §2.5 "모든 문장에 태그 필수"를 시스템 수준에서 강제한다.
    Returns: 등록된 query_id 리스트
    """
    if not untagged:
        return []

    registered_ids = []
    # Collect only the NEW violation queries (outside lock to keep lock scope minimal)
    new_violation_queries = []

    # Calculate next DQ-NNN ID: load once, compute max, then build new queries
    data = load_draft_queries(workspace)
    existing = data.get("queries", [])
    max_num = 0
    for q in existing:
        qid = q.get("query_id", "") or q.get("dq_id", "")
        if qid.startswith("DQ-"):
            try:
                max_num = max(max_num, int(qid.split("-")[1]))
            except (IndexError, ValueError):
                pass

    for violation in untagged:
        max_num += 1
        qid = f"DQ-{max_num:03d}"

        # related_segments: 버킷의 segments에서 연결 가능한 것이 있으면 포함
        related = []
        segs = bucket_data.get("segments", [])
        if segs:
            related = [s.get("segment_id", "") for s in segs[:2]]

        query = {
            "query_id": qid,
            "section_id": section_id,
            "question": (f'[OD-9 enforcement] provenance 태그 없는 문단 발견: "{violation["text"][:80]}..."'),
            "query_type": "source_tag_violation",
            "context": violation["text"][:200],
            "status": "open",
            "priority": "high",
            "raised_by": "section-writer",
            "raised_at": utc_now(),
            "related_segments": related,
            "violation_detail": {
                "para_index": violation["para_index"],
                "excerpt": violation["text"],
            },
        }

        new_violation_queries.append(query)
        registered_ids.append(qid)

    # Use FileLock to prevent race conditions during parallel drafting
    # (same mechanism as _locked_draft_queries_update used by normal draft queries)
    dq_path = workspace / "draft_queries.json"
    lock_path = workspace / ".draft_queries.lock"
    with FileLock(str(lock_path), timeout=30):
        data = load_draft_queries(workspace)
        # Keep existing queries; append only new violation queries
        data.setdefault("queries", [])
        data["queries"].extend(new_violation_queries)
        dq_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return registered_ids


# HD-3: source tag counting
PROVENANCE_TAG_RE = re.compile(r"<!--\s*src:(SEG-\d+|CALC-\d+)")


def _count_source_tags(body: str) -> int:
    """Count provenance source tags in draft body."""
    return len(PROVENANCE_TAG_RE.findall(body))


def validate_and_enforce_source_tags(
    workspace: Path,
    section_id: str,
    body: str,
    bucket_data: dict,
) -> tuple[str, dict]:
    """
    grounded draft의 provenance 태그 enforcement를 실행한다.

    1. 태그 없는 문단 탐지
    2. 없으면: body, meta 반환 (변화 없음)
    3. 있으면:
       - source_conflicts에 자동 등록
       - draft_queries.json에 DQ-* 등록
       - body의 태그 없는 문단에 [확인필요: provenance 태그 없음] 삽입

    Returns:
        (enforced_body, enriched_meta)
    """
    untagged = _find_untagged_sentences(body)
    if not untagged:
        return body, {}

    # draft_queries.json에 DQ-* 등록
    dq_ids = _register_source_tag_violations(workspace, section_id, untagged, bucket_data)

    # body 수정 없이 violation만 metadata로 기록 (§5 "자동 플래그" 충족)
    # 재귀 플래그 방지를 위해 marker 삽입 대신 body는 그대로 반환
    meta = {
        "source_tag_violations_detected": True,
        "untagged_paragraph_count": len(untagged),
        "violation_draft_query_ids": dq_ids,
        "first_violation_excerpt": untagged[0]["text"][:200],
    }

    return body, meta


def _infer_priority(question: str) -> str:
    """질문 내용에서 우선순위 추론."""
    critical_keywords = ["미확인", "오류", "불일치", "누락", "严重"]
    high_keywords = ["필요", "요청", "확인", "필요함", "필요한"]
    low_keywords = ["참고", "선택", "보완"]

    q = question.lower()
    if any(k in q for k in critical_keywords):
        return "critical"
    if any(k in q for k in high_keywords):
        return "high"
    if any(k in q for k in low_keywords):
        return "low"
    return "medium"


def _next_dq_id(queries: list[dict]) -> str:
    """다음 사용 가능한 DQ-NNN ID 반환."""
    max_num = 0
    for q in queries:
        query_id = q.get("query_id") or q.get("dq_id") or ""
        if query_id.startswith("DQ-"):
            try:
                num = int(query_id.split("-")[1])
                max_num = max(max_num, num)
            except (IndexError, ValueError):
                pass
    return f"DQ-{max_num + 1:03d}"


def _is_duplicate_query(
    existing_queries: list[dict],
    new_query: dict,
) -> Optional[dict]:
    """
    section_id + question 기준 중복 확인.
    Returns 기존 query 또는 None.
    """
    new_section = new_query.get("section_id", "")
    new_question = new_query.get("question", "").strip()

    for eq in existing_queries:
        if eq.get("section_id") == new_section and eq.get("question", "").strip() == new_question:
            return eq
    return None


def update_draft_queries(
    workspace: Path,
    section_id: str,
    new_queries: list[dict],
) -> list[str]:
    """Public wrapper — delegates to thread-safe locked version."""
    return _locked_draft_queries_update(workspace, section_id, new_queries)


# ─────────────────────────────────────────────────────────────────────────────
# Front Matter 파싱
# ─────────────────────────────────────────────────────────────────────────────


FRONT_MATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_draft_content(
    content: str,
    section_id: str,
) -> tuple[str, dict]:
    """
    LLM 결과에서 초안 본문과 메타를 분리.

    지원하는 front matter 형식:
    1. JSON: {"key": "value", ...}
    2. YAML: key: value

    Returns:
        (draft_body, meta_dict)
    """
    match = FRONT_MATTER_PATTERN.match(content)
    if not match:
        return content.strip(), {}

    front_text = match.group(1).strip()
    body = content[match.end() :].strip()

    # JSON 시도
    try:
        meta = json.loads(front_text)
        if isinstance(meta, dict):
            return body, meta
    except json.JSONDecodeError:
        pass

    # YAML 시도
    try:
        meta = yaml.safe_load(front_text)
        if isinstance(meta, dict):
            return body, meta
    except yaml.YAMLError:
        pass

    # 파싱 실패 시 front matter 없이 본문만 반환
    return content.strip(), {}


# ─────────────────────────────────────────────────────────────────────────────
# 신뢰도 추정
# ─────────────────────────────────────────────────────────────────────────────


def estimate_confidence(meta: dict, content: str) -> float:
    """초안 신뢰도 추정."""
    # meta에서 draft_confidence 우선, 없으면 confidence
    base = meta.get("draft_confidence") or meta.get("confidence") or 0.5

    # placeholders 수
    placeholder_count = content.count("[확인필요")
    placeholder_ratio = placeholder_count / max(len(content.split()), 1)

    # src 태그覆盖率
    src_tag_count = len(re.findall(r"<!-- src:", content))
    src_ratio = src_tag_count / max(len(content.split()), 1) * 10

    penalty = min(placeholder_ratio * 0.3, 0.3)
    bonus = min(src_ratio * 0.1, 0.1)

    final = max(0.0, min(1.0, float(base) - penalty + bonus))
    return round(final, 2)


# ─────────────────────────────────────────────────────────────────────────────
# 폴백 버킷 감지 및 처리
# ─────────────────────────────────────────────────────────────────────────────


def _is_fallback_bucket(bucket_data: dict) -> bool:
    """
    버킷이 폴백 상태인지 감지한다.

    폴백 조건:
    - status == "generated_fallback"
    - segments == [] AND evidence_items == [] (証拠なし)
    - confidence == 0.0

    두 가지 버킷 형식 모두 지원:
    - framework_mapper 출력: segments 필드 사용
    - 기존 테스트/호환: evidence_items 필드 사용

    Returns:
        True if bucket is fallback/empty
    """
    if bucket_data.get("status") == "generated_fallback":
        return True

    segments = bucket_data.get("segments", [])
    evidence_items = bucket_data.get("evidence_items", [])

    # 두 필드 모두 비어있거나 None이어야 폴백으로 판단
    has_segments = bool(segments and len(segments) > 0)
    has_evidence = bool(evidence_items and len(evidence_items) > 0)

    if not has_segments and not has_evidence:
        return True

    if bucket_data.get("confidence", 1.0) == 0.0 and not has_segments and not has_evidence:
        return True

    return False


def _generate_fallback_draft(
    section_id: str,
    section_blueprint: dict,
    section_entry: dict,
) -> tuple[str, dict]:
    """
    LLM 호출 없이 폴백 placeholder-only 초안을 생성한다.

    Returns:
        (draft_content, meta_dict)
    """
    heading_text = section_entry.get("heading_text", section_id)
    depth_level = section_blueprint.get("depth_level", 2)
    fallback_marker = section_blueprint.get("placeholder_policy", {}).get("marker_format", "[확인필요: {reason}]")

    # heading 구성
    heading_prefix = "#" * depth_level
    heading = f"{heading_prefix} {heading_text}"

    # placeholder 문장
    placeholders = [
        " evidencia 세그먼트가 버킷에 포함되어 있지 않습니다. 자세한 내용 컨설턴트 확인 필요.",
        " 데이터 확인 후 수치 반영 필요.",
    ]
    placeholder_text = "\n\n".join(f"- {p}" for p in placeholders)

    body = f"""<!-- anchor:{section_id} -->
{heading}

{fallback_marker.format(reason="버킷에 evidence 세그먼트가 없습니다. P3 framework-mapper 출력 확인 필요.")}

**초안 상태**: 이 섹션은 증거 없이 생성된 폴백 초안입니다. 컨설턴트가 수동으로 증거 투입 후 초안을 보완해야 합니다.

"""
    meta = {
        "section_id": section_id,
        "draft_version": 1,
        "draft_confidence": 0.0,
        "confidence": 0.0,
        "fallback_mode": True,
        "grounding_mode": "fallback",
        "confidence_breakdown": {
            "evidence_coverage": 0.0,
            "numeric_completeness": 0.0,
            "framework_alignment": 0.0,
        },
        "missing_evidence": [
            {
                "description": "버킷에 evidence 세그먼트가 없습니다.",
                "severity": "high",
                "fallback_used": "placeholder_only",
            }
        ],
        "client_confirmation_needed": [
            {
                "point": "증거投入 및 수치 확인 필요",
                "related_segments": [],
                "query_id": None,
            }
        ],
        "source_conflicts": [],
        "placeholders_inserted": [{"location": f"{section_id}, para 1", "marker": "[확인필요: 버킷 evidence 없음]"}],
        "kpi_status_summary": {"confirmed": 0, "provisional": 0, "missing": 0},
        "provenance_tags_count": 0,
        "anchor_tags_count": 1,
    }

    return body, meta


# ─────────────────────────────────────────────────────────────────────────────
# 단일 섹션 작성
# ─────────────────────────────────────────────────────────────────────────────


def write_single_section(
    workspace: Path,
    section_id: str,
    bucket_data: dict,
    blueprint: dict,
    structure_index: dict,
    dispatcher: AgentDispatcher,
    state_manager: StateManager,
) -> dict:
    """
    단일 섹션의 초안을 작성한다.

    Returns:
        {
            "success": bool,
            "section_id": str,
            "draft_path": str,
            "meta_path": str,
            "new_queries": list[str],
            "error": str,
        }
    """
    try:
        # 1. 해당 섹션의 blueprint 항목 찾기
        sections_blueprint = normalize_blueprint_sections(blueprint)
        section_blueprint = sections_blueprint.get(section_id)

        # 2. 해당 섹션의 structure_index 항목 찾기
        section_entry = None
        if isinstance(structure_index, dict):
            for entry in structure_index.get("entries", []):
                if entry.get("section_id") == section_id:
                    section_entry = entry
                    break

        # 3. 폴백 버킷 감지 — LLM 호출 대신 placeholder-only 초안 생성
        if _is_fallback_bucket(bucket_data):
            body, meta = _generate_fallback_draft(
                section_id=section_id,
                section_blueprint=section_blueprint or {},
                section_entry=section_entry or {},
            )

            # draft queries 등록
            extracted_queries = _extract_draft_queries_from_content(body, section_id, bucket_data)
            new_dq_ids = update_draft_queries(workspace, section_id, extracted_queries)

            # 메타 보강
            meta["section_id"] = section_id
            meta["workspace"] = str(workspace)
            meta["generated_at"] = utc_now()
            meta["agent"] = "section-writer"
            meta["fallback_mode"] = True
            meta["new_draft_queries"] = new_dq_ids

            placeholders = re.findall(r"\[확인필요[^\]]*\]", body)
            meta["placeholder_count"] = len(placeholders)
            src_tags = re.findall(r"<!-- src:[^>]+>", body)
            meta["source_tag_count"] = len(src_tags)

            draft_path = save_draft(section_id, body, workspace)
            meta_path = save_draft_meta(section_id, meta, workspace)

            state_manager.update_section_progress(
                section_id=section_id,
                status="drafted",
                draft_version=meta["draft_version"],
                confidence=meta["draft_confidence"],
            )

            log_event(
                event_type="progress",
                agent="section-writer",
                phase="P4",
                section=section_id,
                message=(f"폴백 초안 생성: {section_id} (fallback_mode=True, evidence 없이 LLM 미호출)"),
                run_id="fallback",
                workspace=str(workspace),
            )

            return {
                "success": True,
                "section_id": section_id,
                "draft_path": str(draft_path.relative_to(workspace)),
                "meta_path": str(meta_path.relative_to(workspace)),
                "new_queries": new_dq_ids,
                "placeholder_count": len(placeholders),
                "confidence": 0.0,
                "fallback_mode": True,
            }

        # 4. 컨텍스트 구성 (정상 버킷)
        context = {
            "section_id": section_id,
            "bucket_data": bucket_data,
            "blueprint": section_blueprint or {},
            "structure_entry": section_entry or {},
            "workspace": str(workspace),
            "phase": "P4",
        }

        # 5. 출력 파일
        output_files = [
            f"07_drafts/{section_id}.md",
        ]

        # 6. 에이전트 디스패치
        result = dispatcher.dispatch(
            agent="section-writer",
            context=context,
            output_files=output_files,
            section_id=section_id,
        )

        # 6. 결과 파싱
        if result.success and result.content:
            draft_content = result.content

            # Front matter 파싱 (YAML 또는 JSON)
            body, meta = parse_draft_content(draft_content, section_id)

            # OD-9: provenance 태그 enforcement (§2.5 "모든 문장에 태그 필수")
            # grounded draft에서 태그 없는 문단이 있으면 자동 플래그 + DQ 등록
            body, violation_meta = validate_and_enforce_source_tags(workspace, section_id, body, bucket_data)
            if violation_meta:
                meta["source_tag_violation"] = violation_meta

            # HD-3: grounded bucket source tag validation
            tag_count = _count_source_tags(body)
            if tag_count == 0 and not _is_fallback_bucket(bucket_data):
                meta["grounding_mode"] = "failed"
                meta["draft_confidence"] = 0.0
                meta["draft_status"] = "failed"
                meta["failure_reason"] = "grounded_bucket_but_no_source_tags"
                state_manager.add_blocking_issue(
                    issue={
                        "issue_id": f"BLK-WRITER-{section_id}",
                        "phase": "P4",
                        "description": f"{section_id}: grounded bucket이나 source tag 0개. LLM 응답 품질 문제.",
                        "severity": "high",
                    }
                )
            else:
                meta["grounding_mode"] = "grounded"

            # placeholder에서 draft queries 추출
            extracted_queries = _extract_draft_queries_from_content(body, section_id, bucket_data)
            new_dq_ids = update_draft_queries(workspace, section_id, extracted_queries)

            # 메타 보강
            meta["section_id"] = section_id
            meta["draft_version"] = meta.get("draft_version", 1)
            meta["draft_confidence"] = estimate_confidence(meta, body)
            # backward compatibility: confidence 필드도 동일 값
            meta["confidence"] = meta["draft_confidence"]
            meta["workspace"] = str(workspace)
            meta["generated_at"] = utc_now()
            meta["agent"] = "section-writer"
            meta["run_id"] = result.run_id

            # placeholders 정리
            placeholders = re.findall(r"\[확인필요[^\]]*\]", body)
            meta["placeholders"] = placeholders
            meta["placeholder_count"] = len(placeholders)

            # src 태그 카운트
            src_tags = re.findall(r"<!-- src:[^>]+>", body)
            meta["source_tags"] = src_tags
            meta["source_tag_count"] = len(src_tags)

            # new_draft_queries 등록
            meta["new_draft_queries"] = new_dq_ids

            # new queries 정보
            # draft_queries에서 missing_evidence, client_confirmation_needed 추출
            all_queries = load_draft_queries(workspace)
            section_queries = [
                q
                for q in all_queries.get("queries", [])
                if q.get("section_id") == section_id and q.get("status") == "open"
            ]
            meta["missing_evidence"] = [
                {
                    "description": q.get("question", ""),
                    "severity": q.get("priority", "medium"),
                    "query_id": q.get("query_id"),
                }
                for q in section_queries
                if q.get("query_type") in ("additional_data_request", "numeric_discrepancy")
            ]
            meta["client_confirmation_needed"] = [
                {
                    "point": q.get("question", ""),
                    "related_segments": q.get("related_segments", []),
                    "query_id": q.get("query_id"),
                }
                for q in section_queries
                if q.get("query_type") == "data_confirmation"
            ]
            meta["source_conflicts"] = [
                {
                    "description": q.get("question", ""),
                    "segments": q.get("related_segments", []),
                    "resolution": "pending",
                    "query_id": q.get("query_id"),
                }
                for q in section_queries
                if q.get("query_type") == "numeric_discrepancy"
            ]
            # placeholders_inserted: body에서 [확인필요: ...] 추출
            meta["placeholders_inserted"] = [
                {
                    "location": f"{section_id}, para {_para_num(body, m.start())}",
                    "marker": m.group(0).strip("[]"),
                    "query_id": None,
                }
                for m in re.finditer(r"\[확인필요[^\]]*\]", body)
            ]
            # kpi_status_summary (단순 추정)
            confirmed = len(src_tags)
            provisional = len(placeholders)
            meta["kpi_status_summary"] = {"confirmed": confirmed, "provisional": provisional, "missing": 0}
            # confidence_breakdown 채워주기
            meta["confidence_breakdown"] = {
                "evidence_coverage": min(1.0, len(src_tags) / max(1, len(bucket_data.get("segments", [])))),
                "numeric_completeness": max(0.0, 1.0 - len(placeholders) / max(1, len(re.findall(r"\d+", body)))),
                "framework_alignment": meta.get("draft_confidence", 0.5),
            }

            # 메타 저장
            draft_path = save_draft(section_id, body, workspace)
            meta_path = save_draft_meta(section_id, meta, workspace)

            # 상태 업데이트
            state_manager.update_section_progress(
                section_id=section_id,
                status="drafted",
                draft_version=meta["draft_version"],
                confidence=meta["draft_confidence"],
            )

            # 로그
            log_event(
                event_type="progress",
                agent="section-writer",
                phase="P4",
                section=section_id,
                message=(
                    f"초안 작성 완료: {section_id} "
                    f"confidence={meta['draft_confidence']}, "
                    f"placeholders={len(placeholders)}, "
                    f"new_queries={len(new_dq_ids)}"
                ),
                run_id=result.run_id or "unknown",
                workspace=str(workspace),
            )

            return {
                "success": True,
                "section_id": section_id,
                "draft_path": str(draft_path.relative_to(workspace)),
                "meta_path": str(meta_path.relative_to(workspace)),
                "new_queries": new_dq_ids,
                "placeholder_count": len(placeholders),
                "confidence": meta["draft_confidence"],
            }

        else:
            error_msg = result.error or "LLM 호출 실패"
            state_manager.add_blocking_issue(
                issue={
                    "reason": f"섹션 {section_id} 초안 작성 실패: {error_msg}",
                    "severity": "high",
                    "section_id": section_id,
                },
                agent="section-writer",
                phase="P4",
            )
            return {
                "success": False,
                "section_id": section_id,
                "error": error_msg,
            }

    except Exception as e:
        tb = traceback.format_exc()
        state_manager.add_blocking_issue(
            issue={
                "reason": f"섹션 {section_id} 초안 작성 중 예외: {str(e)}",
                "severity": "blocker",
                "section_id": section_id,
            },
            agent="section-writer",
            phase="P4",
        )
        return {
            "success": False,
            "section_id": section_id,
            "error": f"{str(e)}\n{tb}",
        }


# ─────────────────────────────────────────────────────────────────────────────
# 메인 함수
# ─────────────────────────────────────────────────────────────────────────────


def run_section_writer(
    workspace: str | Path,
    section_ids: Optional[list[str]] = None,
    parallel: bool = True,
    max_workers: int = 3,
) -> dict:
    """
    P4 초안 작성을 실행한다.

    Args:
        workspace: 워크스페이스 경로
        section_ids: 특정 섹션만 작성 (None이면 전체)
        parallel: 섹션별 병렬 실행 여부
        max_workers: 최대 병렬 작업 수

    Returns:
        {
            "success": bool,
            "sections_written": int,
            "outputs": list[str],
            "failed_sections": list[str],
            "new_queries_total": int,
            "message": str,
        }
    """
    workspace = Path(workspace)
    state_manager = StateManager(workspace)

    # 버킷 로드
    buckets = load_buckets(workspace)
    if not buckets:
        return {
            "success": False,
            "sections_written": 0,
            "outputs": [],
            "failed_sections": [],
            "new_queries_total": 0,
            "message": "버킷이 없습니다. P3 framework-mapper를 먼저 실행하세요.",
        }

    # writing_blueprint, structure_index, section_manifest 로드
    blueprint = load_writing_blueprint(workspace)
    structure_index = load_structure_index(workspace)
    section_manifest = load_section_manifest(workspace)

    # manual 섹션 수집 (자동 draft 대상에서 제외)
    manual_section_ids = {
        entry["section_id"] for entry in section_manifest.get("sections", []) if entry.get("writing_mode") == "manual"
    }

    # 대상 섹션 결정 (manual 제외)
    target_section_ids = list(section_ids) if section_ids else list(buckets.keys())
    target_section_ids = [sid for sid in target_section_ids if sid not in manual_section_ids]

    # 이미 초안이 있는 섹션 건너뛰기 (skip existing)
    existing_drafts_dir = workspace / "07_drafts"
    if existing_drafts_dir.is_dir():
        existing_metas = set(f.stem.replace("_meta", "") for f in existing_drafts_dir.glob("SEC-*_meta.json"))
        target_section_ids = [sid for sid in target_section_ids if sid not in existing_metas]

    if not target_section_ids:
        manual_msg = f" ({len(manual_section_ids)}개 manual 섹션 제외)" if manual_section_ids else ""
        return {
            "success": True,
            "sections_written": 0,
            "outputs": [],
            "failed_sections": [],
            "new_queries_total": 0,
            "message": f"모든 섹션의 초안이 이미 존재합니다{manual_msg}.",
        }

    # Dispatcher
    dispatcher = AgentDispatcher(workspace=workspace, state_manager=state_manager)

    # 상태: P4 진행 중
    state_manager.set_phase_status("P4", "in_progress")

    results = []
    outputs = []
    failed_sections = []
    total_new_queries = 0

    if parallel and len(target_section_ids) > 1:
        # 병렬 실행
        with ThreadPoolExecutor(max_workers=min(max_workers, len(target_section_ids))) as executor:
            futures = {}
            for section_id in target_section_ids:
                bucket_data = buckets.get(section_id, {})
                future = executor.submit(
                    write_single_section,
                    workspace,
                    section_id,
                    bucket_data,
                    blueprint,
                    structure_index,
                    dispatcher,
                    state_manager,
                )
                futures[future] = section_id

            for future in as_completed(futures):
                section_id = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    if result["success"]:
                        outputs.append(result["draft_path"])
                        outputs.append(result["meta_path"])
                        total_new_queries += len(result.get("new_queries", []))
                    else:
                        failed_sections.append(section_id)
                except Exception as e:
                    failed_sections.append(section_id)
                    results.append(
                        {
                            "success": False,
                            "section_id": section_id,
                            "error": str(e),
                        }
                    )
    else:
        # 순차 실행
        for section_id in target_section_ids:
            bucket_data = buckets.get(section_id, {})
            result = write_single_section(
                workspace,
                section_id,
                bucket_data,
                blueprint,
                structure_index,
                dispatcher,
                state_manager,
            )
            results.append(result)
            if result["success"]:
                outputs.append(result["draft_path"])
                outputs.append(result["meta_path"])
                total_new_queries += len(result.get("new_queries", []))
            else:
                failed_sections.append(section_id)

    # 상태 갱신
    state_manager.sync()

    sections_written = len(results) - len(failed_sections)

    # 전체 완료 시
    if not failed_sections:
        state_manager.set_phase_status("P4", "complete")

    # 요약 로그
    log_event(
        event_type="milestone",
        agent="section-writer",
        phase="P4",
        message=(
            f"P4 초안 작성 완료: "
            f"{sections_written}/{len(target_section_ids)}개 섹션, "
            f"실패 {len(failed_sections)}개, "
            f"신규 queries {total_new_queries}개"
        ),
        workspace=str(workspace),
    )

    return {
        "success": len(failed_sections) == 0,
        "sections_written": sections_written,
        "total_sections": len(target_section_ids),
        "outputs": outputs,
        "failed_sections": failed_sections,
        "new_queries_total": total_new_queries,
        "message": (
            f"P4 완료: {sections_written}/{len(target_section_ids)}개 섹션 초안 작성됨, "
            f"신규 queries {total_new_queries}개"
        ),
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
    help="작성할 섹션 ID (SEC-X.Y.Z). 미지정 시 전체",
)
@click.option(
    "--no-parallel",
    is_flag=True,
    default=False,
    help="섹션 병렬 실행 비활성화",
)
@click.option(
    "--max-workers",
    "-n",
    type=int,
    default=3,
    help="최대 병렬 작업 수 (default: 3)",
)
def main(
    workspace: Path,
    section_ids: tuple[str, ...],
    no_parallel: bool,
    max_workers: int,
) -> int:
    """P4 초안 작성 스크립트."""
    print(f"[run_section_writer] P4 초안 작성 시작")
    print(f"  workspace  : {workspace}")
    print(f"  sections   : {'all' if not section_ids else ', '.join(section_ids)}")
    print(f"  parallel   : {not no_parallel}")
    print(f"  max_workers: {max_workers}")
    print()

    result = run_section_writer(
        workspace=workspace,
        section_ids=list(section_ids) if section_ids else None,
        parallel=not no_parallel,
        max_workers=max_workers,
    )

    if result["success"]:
        print(f"\n✅ {result['message']}")
        print(f"   Sections written: {result['sections_written']}/{result['total_sections']}")
        print(f"   New queries: {result['new_queries_total']}")
        print(f"   Outputs: {result['outputs'][:6]}")
        if len(result["outputs"]) > 6:
            print(f"            ... +{len(result['outputs']) - 6} more files")
        return 0
    else:
        print(f"\n❌ {result['message']}")
        if result["failed_sections"]:
            print(f"   Failed sections: {result['failed_sections']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
