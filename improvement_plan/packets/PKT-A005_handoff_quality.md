# PKT-A005 — 핸드오프 품질 강화 — 컨설턴트용 체크리스트 자동 생성

## 개요

**문제**: `run_handoff.py`가 현재 `draft_package.json`을 생성하지만 컨설턴트가 핸드오프 패키지를 받았을 때 "무엇을 먼저 봐야 하는지" 즉시 알 수 없다. placeholder 위치, 자료 부족 섹션, 컨설턴트 확인 필요 항목이 분산돼 있다.

**효과**: 이 패킷 완료 후 `09_handoff/` 폴더에 3개의 컨설턴트 가이드 파일이 자동 추가된다. 컨설턴트가 검토 시작 시 이 3개 파일을 먼저 확인하면 우선순위가 즉시 명확해진다.

---

## 입력 파일 (작업 전 반드시 읽기)

1. `scripts/run_handoff.py` — 전체
2. `schemas/draft_meta.schema.json` — meta JSON 구조 파악 (confidence_score, incomplete_segments 등)
3. `workspaces/PRJ-2026-KRS-001/07_drafts/` — 실제 draft meta 파일 구조 확인
4. `workspaces/PRJ-2026-KRS-001/draft_queries.json` — draft query 구조 확인

---

## 상세 작업

### 작업 1. `run_handoff.py` 수정 — 3개 추가 산출물 생성

**백업 먼저**: `cp scripts/run_handoff.py scripts/run_handoff.py.bak`

기존 `run_handoff()` 함수에서 `draft_package.json` 저장 직후, 반환 직전에 아래 3개 파일 생성 로직을 추가한다.

---

### 작업 2. `placeholder_summary.md` 생성

placeholder가 있는 섹션과 그 수를 요약한 마크다운 표.

데이터 수집:
- `07_drafts/` 폴더의 `SEC-*_meta.json` 파일을 순회한다
- 각 meta JSON에서 `incomplete_segments`, `draft_queries`, `confidence_score` 필드를 읽는다
- 해당 `SEC-*.md` 파일에서 `[확인필요]`, `[데이터 없음]`, `[TBD]`, `[PLACEHOLDER]` 등의 패턴을 카운트한다

```python
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
        r"\[확인필요\]", r"\[데이터 없음\]", r"\[TBD\]", r"\[PLACEHOLDER\]",
        r"\[추후 기재\]", r"\[미확인\]", r"\[자료 부족\]",
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
        heading = meta.get("heading_text", "(제목 없음)")
        confidence = meta.get("confidence_score", None)
        incomplete_count = len(meta.get("incomplete_segments", []))
        dq_count = len(meta.get("draft_queries", []))

        # draft MD 파일에서 placeholder 카운트
        draft_md = drafts_dir / f"{section_id}.md"
        placeholder_count = 0
        if draft_md.exists():
            content = draft_md.read_text(encoding="utf-8")
            placeholder_count = len(placeholder_re.findall(content))

        rows.append({
            "section_id": section_id,
            "heading": heading,
            "confidence": confidence,
            "placeholder_count": placeholder_count,
            "incomplete_segments": incomplete_count,
            "draft_queries": dq_count,
        })

    # 마크다운 표 생성
    total_placeholders = sum(r["placeholder_count"] for r in rows)
    total_dq = sum(r["draft_queries"] for r in rows)

    lines = [
        "# Placeholder 요약표",
        "",
        f"> 생성일시: {utc_now()}  ",
        f"> 전체 placeholder: **{total_placeholders}개**, 미확인 Draft Query: **{total_dq}개**",
        "",
        "| 섹션 ID | 제목 | 신뢰도 | Placeholder 수 | 미완료 세그먼트 | Draft Query |",
        "|---------|------|--------|---------------|----------------|-------------|",
    ]

    for r in sorted(rows, key=lambda x: x["placeholder_count"], reverse=True):
        confidence_str = f"{r['confidence']:.1%}" if r["confidence"] is not None else "—"
        lines.append(
            f"| {r['section_id']} | {r['heading']} | {confidence_str} | "
            f"{r['placeholder_count']} | {r['incomplete_segments']} | {r['draft_queries']} |"
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
```

---

### 작업 3. `data_gap_priority.md` 생성

자료 부족 섹션을 우선순위 순으로 정리한 마크다운 파일.

데이터 수집:
- `02_file_registry/data_gap_report.json`에서 변환 실패 파일 목록
- `06_buckets/SEC-*.json`에서 각 섹션의 `grounded_segments` 수
- `05_planning/writing_blueprint.json`에서 섹션별 `required_evidence_count` 또는 `evidence_priority`

```python
def _generate_data_gap_priority(workspace: Path, outputs: list[str]) -> None:
    """
    09_handoff/data_gap_priority.md 생성.
    증거 충족도가 낮은 섹션을 우선순위 순으로 표시.
    """
    handoff_dir = workspace / "09_handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)

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
        heading = sec_info.get("heading_text", "(제목 없음)")

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

        gap_rows.append({
            "section_id": sid,
            "heading": heading,
            "evidence_priority": required,
            "actual_segments": actual_count,
            "gap_level": gap_level,
            "sort_priority": priority,
        })

    gap_rows.sort(key=lambda x: (x["sort_priority"], x["section_id"]))

    # 마크다운 생성
    lines = [
        "# 자료 부족 섹션 우선순위표",
        "",
        f"> 생성일시: {utc_now()}",
        "",
        "## 섹션별 증거 충족도",
        "",
        "| 우선순위 | 섹션 ID | 제목 | 증거 세그먼트 수 | 충족도 |",
        "|----------|---------|------|----------------|-------|",
    ]

    for r in gap_rows:
        lines.append(
            f"| {r['sort_priority']} | {r['section_id']} | {r['heading']} | "
            f"{r['actual_segments']} | {r['gap_level']} |"
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
```

---

### 작업 4. `consultant_review_checklist.json` 생성

컨설턴트가 수행해야 할 검토 항목 Top N을 JSON으로 정리.

```python
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
                    checklist_items.append({
                        "type": "draft_query",
                        "id": q.get("query_id", "DQ-???"),
                        "section_id": q.get("section_id"),
                        "priority": q.get("priority", "medium"),
                        "description": q.get("question", q.get("description", "")),
                        "action_required": "원본 자료에서 수치/사실 확인 후 [확인필요] 교체",
                        "status": "open",
                    })
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # 2. confidence_score < 0.5인 섹션 추가
    drafts_dir = workspace / "07_drafts"
    for meta_path in sorted(drafts_dir.glob("SEC-*_meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            score = meta.get("confidence_score")
            if score is not None and score < 0.5:
                checklist_items.append({
                    "type": "low_confidence_section",
                    "id": meta.get("section_id", meta_path.stem),
                    "section_id": meta.get("section_id"),
                    "priority": "high" if score < 0.3 else "medium",
                    "description": f"신뢰도 낮음: {score:.1%} — {meta.get('heading_text', '')}",
                    "action_required": "섹션 내용 전체 검토 및 부정확한 서술 수정",
                    "status": "open",
                })
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
```

---

### 작업 5. `run_handoff()` 함수에 3개 함수 호출 추가

기존 `run_handoff()` 함수에서 `draft_package.json` 저장 후, 반환 전에 추가:

```python
    # ── 핸드오프 품질 강화 산출물 생성 ──
    _generate_placeholder_summary(workspace, outputs)
    _generate_data_gap_priority(workspace, outputs)
    _generate_consultant_review_checklist(workspace, outputs)
```

---

## 완료 기준 체크리스트

```bash
# 1. run_handoff 실행
uv run python scripts/run_handoff.py --workspace workspaces/PRJ-2026-KRS-001

# 2. 3개 파일 생성 확인
ls -la workspaces/PRJ-2026-KRS-001/09_handoff/placeholder_summary.md
ls -la workspaces/PRJ-2026-KRS-001/09_handoff/data_gap_priority.md
ls -la workspaces/PRJ-2026-KRS-001/09_handoff/consultant_review_checklist.json

# 3. 내용 확인 (비어있지 않아야 함)
wc -l workspaces/PRJ-2026-KRS-001/09_handoff/placeholder_summary.md
cat workspaces/PRJ-2026-KRS-001/09_handoff/consultant_review_checklist.json | python3.13 -m json.tool

# 4. 기존 테스트 회귀 없음 확인
uv run pytest tests/ -x -q
```

---

## 결정 원칙

- `07_drafts/` 또는 `06_buckets/`이 비어 있어도 함수는 오류 없이 빈 표를 생성한다.
- `data_gap_priority.md`에서 `writing_blueprint.json`이 없으면 섹션 목록 없이 변환 실패 파일 섹션만 출력한다.
- `consultant_review_checklist.json`은 `draft_queries.json`이 없어도 low_confidence 섹션에서 항목을 수집한다.
- emoji(🔴🟡🟢) 사용은 컨설턴트 가시성을 위한 것이므로 유지한다.
- 파일 생성 실패(권한 오류 등)는 오류를 로그에 기록하고 `run_handoff()`의 전체 성공 여부에는 영향을 주지 않는다 (`try/except`로 감싸서 경고 수준으로 처리).
