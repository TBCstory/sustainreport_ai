#!/usr/bin/env python3
"""
migrate_draft_meta.py

기존 SEC-*_meta.json 파일을 정규 필드 계약(draft_meta.schema.json 기준)으로 변환.

사용법:
    python scripts/migrate_draft_meta.py [--dry-run | --apply] <workspace>

옵션:
    --dry-run  변환 결과를 stdout에 출력만 (파일 수정 없음)
    --apply    실제 파일 갱신 (원본은 .bak 백업)
    --verbose  변경된 필드 상세 출력
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

# ── 필드 별칭 매핑 (구버전 → 정규) ────────────────────────────────────────────
FIELD_ALIASES: dict[str, str] = {
    # 제목
    "heading_text": "heading_ko",
    "section_title": "heading_ko",
    "title": "heading_ko",
    # 신뢰도
    "confidence_score": "draft_confidence",
    "confidence": "_confidence_string",  # 문자열 → 숫자 변환 필요
    # 증거
    "evidence_segments_used": "evidence_segments",
    "evidence_used": "evidence_segments",
    "grounded_segments": "evidence_segments",
    # placeholder
    "placeholders_inserted": "placeholders",
}

CONFIDENCE_STRING_MAP: dict[str, float] = {
    "high": 0.85,
    "medium": 0.55,
    "low": 0.25,
}

# 정규 required 필드
REQUIRED_FIELDS = [
    "section_id",
    "draft_version",
    "heading_ko",
    "draft_confidence",
    "evidence_segments",
    "placeholders",
    "missing_evidence",
    "created_at",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_field_names(data: dict) -> tuple[dict, list[str]]:
    """
    구버전 필드명을 정규 필드명으로 변환.
    Returns: (normalized_data, list_of_changes)
    """
    changes: list[str] = []
    normalized = dict(data)

    # 1. 별칭 필드 처리
    for old_key, new_key in FIELD_ALIASES.items():
        if old_key in normalized and new_key not in normalized:
            normalized[new_key] = normalized.pop(old_key)
            changes.append(f"  {old_key} → {new_key}")

    # 2. confidence 문자열 → 숫자 변환
    if "_confidence_string" in normalized:
        raw = normalized.pop("_confidence_string")
        numeric = CONFIDENCE_STRING_MAP.get(raw, 0.5)
        normalized["draft_confidence"] = numeric
        changes.append(f"  confidence '{raw}' → draft_confidence {numeric}")

    # 3. placeholders가 객체 배열인 경우 → 문자열 배열로 변환
    if "placeholders" in normalized:
        raw_placeholders = normalized["placeholders"]
        if raw_placeholders and isinstance(raw_placeholders, list):
            first = raw_placeholders[0]
            if isinstance(first, dict):
                # {"location": "...", "label": "..."} → "location: label"
                normalized["placeholders"] = [
                    f"{p.get('location', '?')}: {p.get('label', '[추후 기재]')}" for p in raw_placeholders
                ]
                changes.append(f"  placeholders: {len(raw_placeholders)} 객체 → 문자열 배열")

    # 4. draft_version이 없으면 1로 기본
    if "draft_version" not in normalized:
        normalized["draft_version"] = 1
        changes.append("  draft_version: 기본값 1 설정")

    # 5. created_at이 없으면 현재 시각
    if "created_at" not in normalized:
        normalized["created_at"] = utc_now()
        changes.append("  created_at: 현재 시각 설정")

    # 6. agent 필드가 author 대신 있는 경우 유지
    if "author" in normalized and "agent" not in normalized:
        normalized["agent"] = normalized.pop("author")
        changes.append("  author → agent")

    # 7. status 정규화 (스키마의 enum 값으로)
    if "status" in normalized:
        status_map = {
            "in_progress": "in_progress",
            "review": "review",
            "approved": "approved",
            "rejected": "rejected",
            "draft_complete": "draft_complete",
        }
        old_status = normalized["status"]
        normalized["status"] = status_map.get(old_status, old_status)

    return normalized, changes


def migrate_file(
    meta_path: Path,
    dry_run: bool = False,
    verbose: bool = False,
) -> tuple[bool, list[str]]:
    """
    단일 _meta.json 파일을 변환.
    Returns: (changed: bool, changes: list[str])
    """
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return False, [f"  오류: 읽기 실패 — {e}"]

    # 정규화
    normalized, changes = normalize_field_names(data)

    # 필수 필드 누락 확인
    missing_fields = [f for f in REQUIRED_FIELDS if f not in normalized]
    if missing_fields:
        changes.append(f"  ⚠️  필수 필드 누락: {missing_fields}")

    if not changes:
        return False, ["  변경사항 없음 (이미 정규화 상태)"]

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"파일: {meta_path.name}")
        for c in changes:
            print(c)
        print("  정규화 후 필드:")
        for k, v in normalized.items():
            if isinstance(v, list) and len(v) > 3:
                print(f"    {k}: [{len(v)} items]")
            elif isinstance(v, dict):
                print(f"    {k}: {{...{len(v)} keys}}")
            else:
                print(f"    {k}: {repr(v)[:80]}")

    if dry_run:
        print(f"  [DRY-RUN] {meta_path.name} — 변경 적용 안 함")
        return True, changes

    # 실제 적용: 백업 → 쓰기
    bak_path = meta_path.with_suffix(meta_path.suffix + ".bak")
    shutil.copy2(meta_path, bak_path)

    output = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    meta_path.write_text(output, encoding="utf-8")

    return True, changes


def main() -> None:
    parser = argparse.ArgumentParser(description="draft_meta.json을 정규 필드 계약으로 변환")
    parser.add_argument(
        "workspace",
        type=Path,
        help="프로젝트 워크스페이스 경로 (예: workspaces/PRJ-2026-KRS-001)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="변환 결과를 stdout에 출력만 (파일 수정 없음)",
    )
    group.add_argument(
        "--apply",
        action="store_true",
        help="실제 파일 갱신 (원본은 .bak 백업)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="변경된 필드 상세 출력")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("(--dry-run 또는 --apply) 중 하나를 지정해야 합니다.")

    workspace: Path = args.workspace
    drafts_dir = workspace / "07_drafts"

    if not drafts_dir.is_dir():
        print(f"오류: {drafts_dir} 디렉토리가 존재하지 않습니다.")
        raise SystemExit(1)

    meta_files = sorted(drafts_dir.glob("SEC-*_meta.json"))
    if not meta_files:
        print(f"변환 대상 파일 없음: {drafts_dir}")
        raise SystemExit(0)

    mode_label = "[DRY-RUN]" if args.dry_run else "[APPLY]"
    print(f"{mode_label} 시작 — 작업 디렉토리: {workspace}")
    print(f"  대상 파일: {len(meta_files)}개")

    total_changed = 0
    total_unchanged = 0

    for meta_path in meta_files:
        changed, changes = migrate_file(
            meta_path,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        if changed:
            total_changed += 1
        else:
            total_unchanged += 1

    print(f"\n결과: {total_changed}개 변환됨, {total_unchanged}개 변경 없음")
    if args.apply:
        print("  백업 파일(*.bak)은 원본 디렉토리에 보관됩니다.")


if __name__ == "__main__":
    main()
