# PKT-003: toc-planner 목차 논의 단계 추가

## 목표
toc-planner가 `intake_manifest.json`을 참조하여:
1. 목차 초안을 **컨설턴트에게 먼저 보여주고 승인받는** 단계를 명시화
2. 목차 스타일(프레임워크/테마/커스텀)에 따라 다르게 설계할 수 있는 로직 추가
3. 이중중대성 평가 결과가 있으면 섹션 깊이 배분에 반영

## 입력 파일
- `/Users/lj_homemac/tools/sustainreport_ai/agents/toc-planner.md` (수정 대상)
- PKT-001에서 생성된 `agents/intake-interviewer.md` (참조)

## 출력 파일
1. **수정**: `agents/toc-planner.md` (백업 후 수정)
2. **신규 산출물 명세** — toc-planner가 추가로 생성할 파일: `05_planning/toc_draft.json`

---

## 상세 작업

### STEP 1: `agents/toc-planner.md` 백업

```bash
cp /Users/lj_homemac/tools/sustainreport_ai/agents/toc-planner.md \
   /Users/lj_homemac/tools/sustainreport_ai/agents/toc-planner.md.bak
```

### STEP 2: `agents/toc-planner.md` 수정

#### 2-1. `## 입력 계약` 테이블에 행 추가

기존 테이블에 다음 행을 추가한다 (필수 항목으로):

```
| `00_definition/intake_manifest.json` | 인테이크 인터뷰 결과 (목차 방식, 포함범위, 스타일 등) | **필수** |
| `02_file_registry/data_gap_report.json` | 섹션별 데이터 충족도 (깊이 배분 참조) | 존재시 |
```

#### 2-2. `## 작업 규칙` 최상단에 다음 섹션 삽입

```markdown
### 0단계: 사전 입력 확인 (intake_manifest 참조)

작업 시작 전 반드시 실행한다.

1. `00_definition/intake_manifest.json` 읽기
   - 파일이 없으면 **즉시 중단**: 오케스트레이터에게 "인테이크 인터뷰가 완료되지 않았습니다. intake-interviewer 에이전트를 먼저 실행하세요" 보고
   - 파일이 있으면 다음 필드를 추출:
     - `A_structure.toc_style` → 목차 구성 방식 결정
     - `A_structure.scope_inclusions` / `scope_exclusions` → 포함/제외 섹션 확정
     - `A_structure.section_priority` → 우선 섹션 깊이 배분
     - `B_style.narrative_style` → 각 섹션 서술 방향 메모
     - `C_references.high_materiality_topics` → 고중대성 토픽 확인

2. `02_file_registry/data_gap_report.json` 읽기 (있는 경우)
   - `summary.low_readiness` 섹션은 `depth: "standard"` 이하로 설정 권고
   - `summary.critical_missing` 항목은 writing_blueprint의 `placeholder_policy`에 반영

### 1단계: 목차 초안 생성 (컨설턴트 승인 전)

intake_manifest의 `toc_style` 에 따라 다음 방식으로 목차를 구성한다:

#### toc_style = "framework"
프레임워크(KSSB/GRI) 기준 항목 순서로 구성한다.
예: 고용(S1) → 안전보건(S2) → 인권(S3) → 사회공헌(S4)

#### toc_style = "theme"
사업 테마 중심으로 구성한다. 독자 친화적 스토리라인을 만든다.
예: 안전한 일터 만들기 → 사람 중심 경영 → 지역사회 공존

테마형 목차에서는 여러 프레임워크 토픽이 하나의 장(章)으로 묶일 수 있다.
이 경우 `structure_index.json`의 `framework_mappings`를 조정한다.

#### toc_style = "custom"
`A_structure.custom_toc_reference` 에 지정된 파일을 읽고, 해당 목차 구조를 기반으로
섹션 ID를 부여하고 프레임워크 매핑을 추가한다.

#### 목차 초안 파일 저장
`05_planning/toc_draft.json` 에 저장한다:

```json
{
  "draft_version": 1,
  "toc_style": "framework | theme | custom",
  "based_on_intake": "INTAKE-PRJ-YYYY-CODE-NNN",
  "sections": [
    {
      "proposed_section_id": "SEC-1",
      "heading_ko": "제안 제목",
      "heading_en": "Proposed Title",
      "level": 1,
      "parent_id": null,
      "rationale": "왜 이 섹션을 이 위치에 두는지 한 줄 설명",
      "proposed_depth": "brief | standard | deep",
      "depth_rationale": "intake priority 또는 data_gap 기반 판단"
    }
  ],
  "exclusions": [
    {
      "topic": "협력사",
      "reason": "intake_manifest scope_exclusions 기준"
    }
  ],
  "consultant_approval": "pending"
}
```

### 2단계: 컨설턴트 승인 요청

목차 초안을 컨설턴트가 읽기 쉬운 형태로 출력하고 승인을 요청한다.

출력 형식:

```
📋 목차 초안 — 검토 및 승인 요청

구성 방식: {toc_style}

## 제안 목차

{섹션 번호}. {제목 (한글)} / {제목 (영문)}
   깊이: {brief/standard/deep} | 이유: {rationale}
   ...

## 제외 항목
- {토픽}: {이유}

---
이 목차 구조로 진행할까요?
수정이 필요한 섹션이 있으면 말씀해주세요.
(예: "3번 섹션 제목을 '안전보건체계 고도화'로 바꿔주세요", "4번과 5번 순서를 바꿔주세요")
```

컨설턴트가 승인하면:
1. `toc_draft.json` 의 `consultant_approval` 를 `"approved"` 로 변경
2. 오케스트레이터에게 "목차 승인됨, writing_blueprint 생성 준비 완료" 보고

컨설턴트가 수정 요청하면:
1. 수정 사항을 반영하여 `draft_version` 을 +1
2. 다시 출력하여 재승인 요청

### 3단계: writing_blueprint 생성 (기존 로직 — toc 승인 후)

기존 writing_blueprint 생성 로직을 그대로 실행한다.
단, 다음 항목을 intake_manifest에서 가져와 반영한다:

- `narrative_style` → 각 섹션의 `writing_approach` 기본값 설정
  - `"activity"` → "2024년 주요 활동과 성과를 중심으로 서술"
  - `"framework"` → "제도·정책·체계를 중심으로 서술"
  - `"mixed"` → 섹션별 `mixed_section_map` 참조
- `sentence_ending` → `style_override.sentence_ending` 에 기록
- `company_name_rule` → `style_override.company_name_rule` 에 기록
- `must_include_achievements` → 각 관련 섹션의 `key_facts` 에 추가
```

---

### STEP 3: `05_planning/toc_draft.json` 을 신규 산출물로 등록

`orchestration/agent_contracts.json` 파일을 읽고,
toc-planner의 출력 계약에 `toc_draft.json` 항목을 추가한다.

파일이 없으면 신규 생성하지 않고, 해당 내용을 toc-planner.md의 `## 출력 계약` 섹션에 추가한다:

```markdown
### 3. 목차 초안: `05_planning/toc_draft.json`

컨설턴트 승인 전 목차 초안. `consultant_approval: "pending"` 상태로 생성.
승인 후 `"approved"` 로 변경. writing_blueprint 생성의 선행 조건.
```

---

## 완료 기준

1. `agents/toc-planner.md.bak` 이 존재한다
2. `agents/toc-planner.md` 에 "0단계: 사전 입력 확인" 섹션이 포함된다
3. `agents/toc-planner.md` 에 "1단계: 목차 초안 생성" 섹션이 포함된다
4. `agents/toc-planner.md` 에 "2단계: 컨설턴트 승인 요청" 섹션이 포함된다
5. `toc_draft.json` 이 출력 계약에 포함된다
6. 기존 writing_blueprint 생성 로직은 삭제하지 않고 "3단계" 로 명칭만 변경한다

---

## 결정 원칙

- toc_style에 따른 분기는 명확히 구분한다. 기본값은 "framework"
- `consultant_approval` 는 반드시 컨설턴트의 명시적 승인("응", "OK", "맞아" 등) 후에만 "approved"로 변경
- 섹션 깊이 기준: brief = 200~400자, standard = 600~1000자, deep = 1200자 이상
