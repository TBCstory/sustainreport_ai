# PKT-B004: run_handoff.py 산출물 품질 수정 — 실제 필드 기반 집계

## 목표
run_handoff.py의 3개 산출물 생성 함수가 PKT-B002에서 통일된 **정규 필드명**을 사용하여 실제로 유용한 결과물을 생성하게 만든다.

## 전제 조건
**PKT-B002 완료 필수**. draft_meta 정규 필드명이 확정돼야 이 패킷을 실행할 수 있음.

PKT-B002에서 확정된 정규 필드명:
- 제목: `heading_ko`
- 신뢰도: `draft_confidence` (number 0-1)
- 증거: `evidence_segments` (string[])
- placeholder: `placeholders` (string[])
- 미확보 증거: `missing_evidence` (string[])

Blueprint 정규 필드명:
- 제목: `heading_ko`

## 입력 파일 (반드시 먼저 읽을 것)
- `/Users/lj_homemac/tools/sustainreport_ai/scripts/run_handoff.py` — 전체 (특히 line 580-830)
- `/Users/lj_homemac/tools/sustainreport_ai/schemas/draft_meta.schema.json` — PKT-B002에서 업데이트된 버전
- 실제 산출물: `workspaces/PRJ-2026-KRS-001/09_handoff/` 아래 파일들

## 상세 작업

### 작업 1: _generate_placeholder_summary 수정

**위치**: `run_handoff.py` ~line 580-610

**수정 포인트:**
```python
# line 595: 변경 전
heading = meta.get("heading_text", "(제목 없음)")
# line 595: 변경 후
heading = meta.get("heading_ko", "(제목 없음)")

# line 596: 변경 전
confidence = meta.get("confidence_score", None)
# line 596: 변경 후
confidence = meta.get("draft_confidence", None)

# line 597: 변경 전 (있다면)
incomplete_count = len(meta.get("incomplete_segments", []))
# line 597: 변경 후
placeholder_count = len(meta.get("placeholders", []))
```

**추가**: placeholder 목록을 마크다운 테이블에 개별 항목으로 출력. 현재 count만 보여주는데, 실제 placeholder 텍스트를 보여줘야 컨설턴트가 바로 확인할 수 있음.

### 작업 2: _generate_data_gap_priority 수정

**위치**: `run_handoff.py` ~line 680-730

**수정 포인트:**
```python
# line 700-702: blueprint에서 heading 읽기
# 변경 전
heading = sec_info.get("heading_text", "(제목 없음)")
# 변경 후
heading = sec_info.get("heading_ko", "(제목 없음)")
```

**추가 개선 — review_priority_score**:
각 섹션에 대해 우선순위 점수를 계산하여 "먼저 볼 섹션" 자동 정렬:

```python
def _calc_review_priority(meta: dict, blueprint_section: dict) -> float:
    """높을수록 먼저 검토 필요. 0-100 scale."""
    score = 0.0

    # 1. 신뢰도 역수 (낮을수록 높은 점수)
    confidence = meta.get("draft_confidence", 0.5)
    score += (1.0 - confidence) * 40  # max 40

    # 2. placeholder 수
    placeholders = len(meta.get("placeholders", []))
    score += min(placeholders * 5, 30)  # max 30

    # 3. 미확보 증거 수
    missing = len(meta.get("missing_evidence", []))
    score += min(missing * 5, 20)  # max 20

    # 4. 증거 부족 (evidence_segments 비어있음)
    if not meta.get("evidence_segments"):
        score += 10  # max 10

    return round(min(score, 100), 1)
```

gap_rows에 `review_priority_score` 컬럼 추가. 출력 시 이 점수 내림차순 정렬.

### 작업 3: _generate_consultant_review_checklist 수정

**위치**: `run_handoff.py` ~line 800-830

**수정 포인트:**
```python
# line 810: 변경 전
score = meta.get("confidence_score")
# line 810: 변경 후
score = meta.get("draft_confidence")

# line 818: 변경 전
"description": f"신뢰도 낮음: {score:.1%} — {meta.get('heading_text', '')}"
# line 818: 변경 후
"description": f"신뢰도 낮음: {score:.1%} — {meta.get('heading_ko', '')}"
```

**추가 체크리스트 항목:**
- `missing_evidence`가 3개 이상인 섹션 → `type: "data_collection_needed"` 항목 추가
- `placeholders`가 5개 이상인 섹션 → `type: "heavy_placeholder_section"` 항목 추가

### 작업 4: alias fallback 패턴 적용

모든 meta 읽기 함수에 다음 helper 적용:

```python
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

# 사용 예:
heading = _read_meta_field(meta, "heading_ko", ["heading_text", "section_title", "title"], "(제목 없음)")
confidence = _read_meta_field(meta, "draft_confidence", ["confidence_score", "confidence"], None)
```

이렇게 하면 마이그레이션 전 산출물도 읽을 수 있음.

`confidence`가 문자열인 경우 숫자 변환:
```python
if isinstance(confidence, str):
    confidence = {"high": 0.85, "medium": 0.55, "low": 0.25}.get(confidence, 0.5)
```

### 작업 5: 출력 검증

수정 완료 후 샘플 워크스페이스(`PRJ-2026-KRS-001`)에서 run_handoff.py 실행하여:
1. `placeholder_summary.md` — 제목이 실제 한국어 제목으로 표시되는지 확인
2. `data_gap_priority.md` — confidence가 실제 숫자로 표시, review_priority_score 포함
3. `consultant_review_checklist.json` — 항목이 비어있지 않은지 확인, heading_ko 값 확인

## 완료 기준
1. 샘플 워크스페이스에서 `(제목 없음)` 출력이 **완전히 사라짐**
2. confidence가 실제 값(숫자)으로 출력됨
3. evidence count가 > 0 (증거가 있는 섹션)
4. consultant_review_checklist.json에 항목이 존재
5. review_priority_score가 각 섹션에 계산됨
6. `uv run pytest tests/ -q` — 전체 통과

## 결정 원칙
- alias fallback은 방어적으로: 정규 키가 없을 때만 시도. 정규 키가 있으면 alias 무시
- confidence 문자열→숫자 변환 시 매핑에 없는 값: 0.5 기본값 + 경고 출력
- review_priority_score 계산은 휴리스틱: 완벽할 필요 없고, "대략 맞는 순서"면 충분
- draft_package.json이 존재하면 1차 소스로 사용하는 것이 이상적이나, 없을 경우 개별 meta fallback

## 영향 범위
- `scripts/run_handoff.py` — 주 수정 대상 (3개 함수 + helper 1개)
- 기존 테스트 중 handoff 관련이 있으면 수정
- 새 테스트는 PKT-B005에서 추가
