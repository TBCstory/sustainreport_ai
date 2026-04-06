# PKT-B002: draft_meta 필드 계약 통일 — 스키마·section-writer·run_handoff 3원 정합

## 목표
draft_meta.schema.json, section-writer 에이전트, run_handoff.py, run_section_writer.py가 **동일한 필드명**을 사용하도록 통일한다.

## 문제 진단

현재 draft meta 필드가 3원 불일치 상태:

| 개념 | draft_meta.schema.json (스키마) | 실제 산출물 (SEC-2.4_meta) | 실제 산출물 (SEC-3_meta) | 실제 산출물 (SEC-5.1_meta) | run_handoff.py (코드) |
|------|------|------|------|------|------|
| 제목 | (없음) | (없음) | `heading_ko` | `section_title` | `heading_text` |
| 신뢰도 | `confidence_score` (0-1) | `draft_confidence` (0-1) | `confidence` ("medium") | `confidence` ("medium") | `confidence_score` |
| 증거 목록 | (없음) | (없음) | `evidence_segments_used` | `evidence_used` | `grounded_segments` |
| placeholder 목록 | (없음) | `placeholders_inserted` (문자열[]) | (없음) | `placeholders` (객체[]) | `incomplete_segments` |
| blueprint 참조 | (없음) | (없음) | (없음) | (없음) | `heading_text` (blueprint에서) |

**blueprint의 필드도 불일치:**
- writing_blueprint.schema.json: `title`
- 실제 blueprint: `heading_ko`
- run_handoff.py: `heading_text`

## 입력 파일 (반드시 먼저 읽을 것)
- `/Users/lj_homemac/tools/sustainreport_ai/schemas/draft_meta.schema.json`
- `/Users/lj_homemac/tools/sustainreport_ai/schemas/writing_blueprint.schema.json`
- `/Users/lj_homemac/tools/sustainreport_ai/agents/section-writer.md` — meta 출력 지시 확인
- `/Users/lj_homemac/tools/sustainreport_ai/scripts/run_section_writer.py` — meta 생성 로직
- `/Users/lj_homemac/tools/sustainreport_ai/scripts/run_handoff.py` — meta 읽기 로직
- 실제 산출물 3개:
  - `workspaces/PRJ-2026-KRS-001/09_handoff/drafts/SEC-2.4_meta.json`
  - `workspaces/PRJ-2026-KRS-001/09_handoff/drafts/SEC-3_meta.json`
  - `workspaces/PRJ-2026-KRS-001/09_handoff/drafts/SEC-5.1_meta.json`

## 상세 작업

### 작업 1: 정규 필드명 결정

다음을 **정규 필드명**으로 확정한다. 이 결정은 이 패킷 이후 모든 코드·스키마·에이전트 프롬프트에 적용:

| 개념 | 정규 필드명 | 타입 | 설명 |
|------|-----------|------|------|
| 섹션 제목 (한국어) | `heading_ko` | string | writing_blueprint, structure_index, draft_meta 모두 동일 |
| 섹션 제목 (영어, 선택) | `heading_en` | string \| null | 선택 필드 |
| 신뢰도 점수 | `draft_confidence` | number (0-1) | 통합 신뢰도 (confidence_score 대체) |
| 신뢰도 분해 | `confidence_breakdown` | object \| null | evidence_coverage, numeric_completeness, framework_alignment |
| 증거 세그먼트 ID 목록 | `evidence_segments` | string[] | 사용된 SEG-NNNNN 목록 |
| placeholder 목록 | `placeholders` | string[] | placeholder 텍스트 문자열 배열 (단순 문자열 통일) |
| 미확보 증거 | `missing_evidence` | string[] | 미확보 데이터 설명 목록 |

**왜 이 이름인가:**
- `heading_ko`: 한국어 보고서이므로 언어 명시가 자연스러움. 실제 산출물 다수가 이미 사용
- `draft_confidence`: `confidence_score`보다 명확 (score가 무엇의 score인지 모호). 이미 SEC-2.4 등에서 사용
- `evidence_segments`: `evidence_segments_used`/`evidence_used`/`grounded_segments` 통일. 가장 간결

### 작업 2: draft_meta.schema.json 재정의

**파일**: `schemas/draft_meta.schema.json`

required 필드를 현실에 맞게 조정:
```json
{
  "required": [
    "section_id",
    "draft_version",
    "heading_ko",
    "draft_confidence",
    "evidence_segments",
    "placeholders",
    "missing_evidence",
    "created_at"
  ],
  "properties": {
    "section_id": { "type": "string", "pattern": "^SEC-\\d+(\\.\\d+)*$" },
    "draft_version": { "type": "integer", "minimum": 1 },
    "heading_ko": { "type": "string" },
    "heading_en": { "type": ["string", "null"], "default": null },
    "draft_confidence": { "type": "number", "minimum": 0, "maximum": 1 },
    "confidence_breakdown": {
      "type": ["object", "null"],
      "properties": {
        "evidence_coverage": { "type": "number", "minimum": 0, "maximum": 1 },
        "numeric_completeness": { "type": "number", "minimum": 0, "maximum": 1 },
        "framework_alignment": { "type": "number", "minimum": 0, "maximum": 1 }
      }
    },
    "evidence_segments": {
      "type": "array",
      "items": { "type": "string", "pattern": "^SEG-\\d{5}$" }
    },
    "placeholders": {
      "type": "array",
      "items": { "type": "string" }
    },
    "missing_evidence": {
      "type": "array",
      "items": { "type": "string" }
    },
    "framework_alignment": {
      "type": ["object", "null"],
      "description": "프레임워크 코드 → 설명 매핑"
    },
    "created_at": { "type": "string", "format": "date-time" },
    "status": {
      "type": "string",
      "enum": ["draft_complete", "in_progress", "review", "approved", "rejected"]
    },
    "agent": { "type": "string", "default": "section-writer" }
  }
}
```

**삭제되는 필드**: `confidence_score`, `evidence_confidence`, `project_id` (meta에 불필요, 워크스페이스 경로에서 유추), `author` (→ `agent`로 대체), `word_count` (→ 선택 필드로 유지), `references` (→ `evidence_segments`로 대체), `framework_disclosures` (→ `framework_alignment`으로 대체)

### 작업 3: writing_blueprint.schema.json의 heading 필드 수정

**파일**: `schemas/writing_blueprint.schema.json`

- `title` → `heading_ko` 로 변경
- 실제 blueprint 파일(PRJ-2026-KRS-001)이 이미 `heading_ko`를 사용하므로, 스키마를 실제에 맞춤

### 작업 4: section-writer 에이전트 프롬프트 갱신

**파일**: `agents/section-writer.md`

meta 출력 지시 부분에서 정규 필드명을 명시:
```
## 메타데이터 출력 (SEC-X_meta.json)

반드시 다음 필드를 포함:
- section_id: "SEC-X.Y"
- draft_version: 1 (정수)
- heading_ko: "섹션 한국어 제목"
- draft_confidence: 0.0~1.0 (숫자)
- confidence_breakdown: { evidence_coverage, numeric_completeness, framework_alignment } (각 0-1)
- evidence_segments: ["SEG-00001", ...] (사용한 세그먼트 ID)
- placeholders: ["[추후 기재] 항목 설명", ...] (문자열 배열)
- missing_evidence: ["부족한 데이터 설명", ...]
- created_at: ISO8601 날짜
```

### 작업 5: 기존 산출물 마이그레이션 스크립트

**신규 파일**: `scripts/migrate_draft_meta.py`

기존 워크스페이스의 SEC-*_meta.json을 정규 필드명으로 변환:

```python
FIELD_ALIASES = {
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

CONFIDENCE_STRING_MAP = {
    "high": 0.85,
    "medium": 0.55,
    "low": 0.25,
}
```

- `--dry-run` 모드: 변환 결과를 stdout에 출력만
- `--apply` 모드: 파일을 실제 갱신 (원본은 `.bak` 백업)
- `placeholders` 필드가 객체 배열인 경우 → 문자열 배열로 변환 (`[{"label": "...", "location": "..."}]` → `["location: label"]`)

### 작업 6: run_section_writer.py meta 생성 로직 확인/수정

**파일**: `scripts/run_section_writer.py`

- LLM 응답에서 meta를 파싱하는 부분을 확인
- 정규 필드명(`heading_ko`, `draft_confidence`, `evidence_segments`, `placeholders`, `missing_evidence`)으로 저장하도록 수정
- alias 매핑: LLM이 옛 이름을 반환할 수 있으므로, 저장 전에 `FIELD_ALIASES`로 정규화

## 완료 기준
1. `schemas/draft_meta.schema.json`이 새 필드명으로 재정의됨
2. `schemas/writing_blueprint.schema.json`에서 `title` → `heading_ko`
3. `agents/section-writer.md`의 meta 출력 지시가 정규 필드명 사용
4. `scripts/migrate_draft_meta.py --dry-run` 실행 시 기존 meta의 변환 결과가 정규 필드명으로 출력됨
5. `uv run pytest tests/ -q` — 전체 통과

## 결정 원칙
- `confidence`가 문자열("medium")인 경우: `CONFIDENCE_STRING_MAP`으로 숫자 변환. 매핑에 없는 값이면 0.5 기본값 + 경고 로그
- `placeholders`가 객체 배열인 경우: `location: label` 형태의 문자열로 변환
- 기존 산출물에 `draft_version`이 없는 경우: 1로 기본 설정
- writing_blueprint의 `target_length_chars`는 현행 유지 (스키마의 `expected_length_range`와 다르지만, 이 패킷 범위 밖)

## 영향 범위
- `schemas/draft_meta.schema.json` — 재정의
- `schemas/writing_blueprint.schema.json` — heading 필드만 수정
- `agents/section-writer.md` — meta 출력 부분만 수정
- `scripts/run_section_writer.py` — meta 저장 로직 수정
- `scripts/migrate_draft_meta.py` — 신규 생성
- PKT-B004가 이 패킷에 의존: run_handoff.py는 B004에서 수정
