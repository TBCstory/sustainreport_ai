# PKT-002: data-analyst 갭 리포트 + 파일 한계 고지 강화

## 목표
파일 투입 단계에서 두 가지를 즉시 수행한다:
1. **파일 처리 불가 항목 즉시 고지** — HWP/미지원 포맷을 발견하면 영향 섹션까지 함께 보고
2. **데이터 갭 리포트 자동 생성** — 어느 섹션에 어떤 데이터가 없는지 가시화

이로 인해 컨설턴트는 초안 완성 후가 아니라 **투입 단계에서** 데이터 공백 규모를 파악하고
대응 방향(추가 자료 수집 vs [추후 기재] 유지)을 결정할 수 있다.

## 입력 파일
- `/Users/lj_homemac/tools/sustainreport_ai/agents/data-analyst.md` (수정 대상)
- `/Users/lj_homemac/tools/sustainreport_ai/orchestration/phase_rules.json` (P1 정의 확인)

## 출력 파일
1. **수정**: `agents/data-analyst.md` (백업 후 수정)
2. **신규 스키마**: `schemas/data_gap_report.schema.json`
3. **신규 스크립트 명세**: `improvement_plan/packets/PKT-002_gap_report_script_spec.md` (스크립트 구현 명세만 작성, 실제 스크립트 구현은 미포함 — 스크립트 구현은 PKT-005에서 처리)

---

## 상세 작업

### STEP 1: `agents/data-analyst.md` 백업 생성

```bash
cp /Users/lj_homemac/tools/sustainreport_ai/agents/data-analyst.md \
   /Users/lj_homemac/tools/sustainreport_ai/agents/data-analyst.md.bak
```

### STEP 2: `agents/data-analyst.md` 수정

기존 파일의 **`## 작업 규칙` 섹션** 앞에 다음 섹션을 삽입한다:

---

삽입할 내용:

```markdown
## 0단계: 파일 처리 가능성 사전 체크 (P1 시작 즉시 실행)

### 목적
자료 투입 전에 처리 불가 파일을 식별하고, 영향을 받는 섹션을 컨설턴트에게 즉시 알린다.
이 단계를 건너뛰면 중요한 데이터가 누락된 채 초안이 완성된다.

### 실행 절차

#### 0-1. 처리 불가 파일 식별
`01_raw/` 디렉토리를 스캔하여 다음 확장자를 가진 파일을 목록화한다:
- `.hwp`, `.hwpx` — markitdown 미지원, 수동 변환 필요
- 변환 시도 후 `segments_count: 0` 인 파일 — OCR 실패 또는 이미지 기반 PDF

#### 0-2. 영향 분석
처리 불가 파일 각각에 대해:
- 파일명·내용 키워드로 어느 토픽 데이터를 담고 있는지 추정
- `05_planning/structure_index.json` 또는 `writing_blueprint.json` 이 있으면 참조
- 없으면 파일명 기반으로 추정 (예: "산업안전보건위원회" → 재해율 관련)

#### 0-3. 고지 보고서 출력 (컨설턴트에게 즉시 표시)
다음 형식으로 오케스트레이터에게 보고한다:

```
⚠️ 처리 불가 파일 발견 — 컨설턴트 확인 필요

| 파일 | 형식 | 추정 데이터 | 영향 가능 섹션 | 우선도 |
|------|------|------------|---------------|--------|
| 산업안전보건위원회_1Q.hwp | HWP | 재해율, 사고 건수 | 안전보건 > 재해현황 | 🔴 높음 |
| 실무협의회의록.hwp | HWP | 노사협의 내용 | 노사관계 | 🟡 보통 |

👉 권장 조치:
1. HWP 파일을 동일한 이름의 .md 파일로 변환하여 01_raw/에 넣어주세요
2. 또는 [추후 기재]로 처리하고 나중에 데이터를 직접 입력하셔도 됩니다
3. 어떻게 하시겠습니까?
```

오케스트레이터는 이 보고를 컨설턴트에게 전달하고 지시를 기다린다.

#### 0-4. 결과 기록
처리 불가 파일 목록을 `02_file_registry/unconvertible_files.json` 에 저장한다:

```json
{
  "scanned_at": "<ISO8601>",
  "unconvertible_files": [
    {
      "filename": "산업안전보건위원회_1Q.hwp",
      "file_type": "hwp",
      "estimated_content_keywords": ["산업재해", "안전보건위원회", "재해율"],
      "estimated_affected_topics": ["안전보건 > 재해 및 사고 현황"],
      "priority": "high",
      "user_decision": "pending"
    }
  ],
  "total_unconvertible": 2,
  "user_notified": true
}
```
```

---

이어서 기존 `## 작업 규칙` 의 **4단계: 세그먼트 추출 검증** 다음에 아래 섹션을 추가한다:

```markdown
### 5단계: 데이터 갭 리포트 생성

모든 파일 변환이 완료된 뒤 (또는 변환 불가 결정이 난 뒤) 실행한다.

#### 5-1. 섹션별 데이터 충족도 계산
`05_planning/structure_index.json` 이 있으면 섹션 목록을 읽는다.
각 섹션에 대해:
- 연결된 버킷(`06_buckets/SEC-*.json`)이 있으면 참조
- 없으면 섹션 `notes` 의 키워드로 세그먼트 검색
- 정량 수치가 필요한 섹션 식별 기준:
  - 섹션 notes에 "수치", "통계", "비율", "건수", "명수" 등 키워드 포함
  - framework_mappings에 GRI 401/403/404/406 등 포함

#### 5-2. 갭 리포트 파일 생성
`02_file_registry/data_gap_report.json` 을 생성한다:

```json
{
  "generated_at": "<ISO8601>",
  "workspace_id": "PRJ-YYYY-CODE-NNN",
  "overall_readiness": "low | medium | high",
  "sections": [
    {
      "section_id": "SEC-3.2",
      "section_title": "재해 및 사고 현황",
      "data_readiness": "low",
      "readiness_score": 0.1,
      "available_segments": ["SEG-00037"],
      "available_segment_types": ["policy", "strategy"],
      "missing_data_types": [
        "재해율(LTIR/TRIR)",
        "재해자 수(연도별)",
        "사고사망 건수",
        "재해 유형별 분류"
      ],
      "missing_data_likely_source": "산업안전보건위원회 서면결의서 (HWP 미변환)",
      "recommended_action": "안전관리팀에 원본 데이터 요청 또는 HWP 변환 후 재투입"
    },
    {
      "section_id": "SEC-2.1",
      "section_title": "임직원 현황",
      "data_readiness": "medium",
      "readiness_score": 0.4,
      "available_segments": ["SEG-00004"],
      "available_segment_types": ["org_structure"],
      "missing_data_types": [
        "성별 임직원 수",
        "고용형태별(정규직/비정규직) 인원",
        "연도별 3개년 추이"
      ],
      "missing_data_likely_source": "인사팀 별도 데이터 파일",
      "recommended_action": "인사팀에 성별·고용형태별 임직원 현황 3개년 데이터 요청"
    }
  ],
  "summary": {
    "total_sections": 19,
    "high_readiness": 5,
    "medium_readiness": 8,
    "low_readiness": 6,
    "critical_missing": [
      "재해율 (안전보건위원회 서면결의서)",
      "임직원 수 성별/형태별 (인사팀)",
      "교육 이수율 (안전관리팀)"
    ]
  }
}
```

#### 5-3. 갭 요약 보고 (컨설턴트에게)
오케스트레이터에게 다음 형식으로 보고한다:

```
📊 데이터 갭 리포트

전체 {N}개 섹션 중:
- 🟢 데이터 충족 ({N}개): {섹션 목록}
- 🟡 부분 확보 ({N}개): {섹션 목록}
- 🔴 데이터 부족 ({N}개): {섹션 목록}

⚠️ 즉시 확보 권장 데이터:
1. {데이터명} → {담당 팀 추정} → 영향 섹션: {SEC-X}
2. {데이터명} → {담당 팀 추정} → 영향 섹션: {SEC-Y}

전체 상세 내용: 02_file_registry/data_gap_report.json
```
```

---

### STEP 3: `schemas/data_gap_report.schema.json` 생성

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "data_gap_report.schema.json",
  "title": "Data Gap Report",
  "type": "object",
  "required": ["generated_at", "workspace_id", "sections", "summary"],
  "properties": {
    "generated_at": { "type": "string", "format": "date-time" },
    "workspace_id": { "type": "string" },
    "overall_readiness": { "type": "string", "enum": ["low", "medium", "high"] },
    "sections": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["section_id", "data_readiness", "readiness_score", "missing_data_types"],
        "properties": {
          "section_id": { "type": "string" },
          "section_title": { "type": "string" },
          "data_readiness": { "type": "string", "enum": ["low", "medium", "high"] },
          "readiness_score": { "type": "number", "minimum": 0, "maximum": 1 },
          "available_segments": { "type": "array", "items": { "type": "string" } },
          "available_segment_types": { "type": "array", "items": { "type": "string" } },
          "missing_data_types": { "type": "array", "items": { "type": "string" } },
          "missing_data_likely_source": { "type": "string" },
          "recommended_action": { "type": "string" }
        }
      }
    },
    "summary": {
      "type": "object",
      "properties": {
        "total_sections": { "type": "integer" },
        "high_readiness": { "type": "integer" },
        "medium_readiness": { "type": "integer" },
        "low_readiness": { "type": "integer" },
        "critical_missing": { "type": "array", "items": { "type": "string" } }
      }
    }
  }
}
```

---

## 완료 기준

1. `agents/data-analyst.md.bak` 이 존재한다
2. `agents/data-analyst.md` 에 "0단계: 파일 처리 가능성 사전 체크" 섹션이 포함된다
3. `agents/data-analyst.md` 에 "5단계: 데이터 갭 리포트 생성" 섹션이 포함된다
4. `schemas/data_gap_report.schema.json` 이 유효한 JSON 파일이다
5. 기존 1~4단계 작업 규칙이 그대로 유지된다 (내용 삭제 없음 확인)

---

## 결정 원칙

- 기존 `data-analyst.md` 내용은 삭제하지 않는다. 삽입·추가만 한다
- "0단계"는 기존 `## 작업 규칙` 헤딩 바로 앞에 삽입한다
- "5단계"는 기존 4단계 다음, `## 불확실성 처리` 섹션 앞에 삽입한다
- 모든 JSON 예시는 실제 구현 시 동적으로 채워지는 플레이스홀더임을 주석으로 명시한다
