# PKT-005: 오케스트레이터 흐름 및 phase_rules 업데이트

## 목표
PKT-001~004에서 설계한 에이전트와 기능들이 실제 파이프라인에 통합되도록:
1. `orchestration/phase_rules.json` 에 P0.5(인테이크), P1.5(목차 논의) 페이즈 추가
2. `orchestration/gate_rules.json` 에 새 게이트 조건 추가
3. `CLAUDE.md` 오케스트레이터 헌법의 워크플로우 파이프라인 설명 업데이트
4. 서브에이전트 일람에 intake-interviewer 추가

## 입력 파일
- `/Users/lj_homemac/tools/sustainreport_ai/CLAUDE.md`
- `/Users/lj_homemac/tools/sustainreport_ai/orchestration/phase_rules.json`
- `/Users/lj_homemac/tools/sustainreport_ai/orchestration/gate_rules.json`
- PKT-001~004 결과물 모두 확인 (agents/*.md 백업 존재 확인)

## 출력 파일
1. **수정**: `orchestration/phase_rules.json`
2. **수정**: `orchestration/gate_rules.json`
3. **수정**: `CLAUDE.md`

---

## 상세 작업

### STEP 1: `orchestration/phase_rules.json` 업데이트

파일을 읽고, 기존 내용을 유지하면서 아래 두 페이즈를 추가한다.

#### P0 다음에 P0.5 추가

```json
{
  "phase_id": "P0.5",
  "name": "인테이크 인터뷰",
  "description": "컨설턴트와 구조화된 대화를 통해 보고서 작성 의사결정 사항 확정",
  "agent": "intake-interviewer",
  "entry_conditions": [
    "P0 완료 (project_charter.json 존재)",
    "01_raw/ 디렉토리 생성 완료"
  ],
  "exit_conditions": [
    "00_definition/intake_manifest.json 생성 완료",
    "intake_manifest.consultant_approval 없음 (인터뷰 단계는 승인 불필요)"
  ],
  "required_outputs": [
    "00_definition/intake_manifest.json"
  ],
  "gate_to_next": "GATE-P05-TO-P1",
  "human_approval_required": false,
  "notes": "인테이크 결과가 없으면 P1 진입 불가"
}
```

#### P1 다음에 P1.5 추가

```json
{
  "phase_id": "P1.5",
  "name": "목차 논의",
  "description": "toc-planner가 목차 초안을 생성하고 컨설턴트 승인을 받는 단계",
  "agent": "toc-planner",
  "entry_conditions": [
    "P1 완료 (file_registry.json 존재, 최소 1개 이상 세그먼트 생성)",
    "02_file_registry/data_gap_report.json 생성 완료",
    "00_definition/intake_manifest.json 존재"
  ],
  "exit_conditions": [
    "05_planning/toc_draft.json 생성 완료",
    "toc_draft.consultant_approval = 'approved'"
  ],
  "required_outputs": [
    "05_planning/toc_draft.json"
  ],
  "gate_to_next": "GATE-P15-TO-P2",
  "human_approval_required": true,
  "approval_type": "toc_approval",
  "notes": "목차 승인 없이 writing_blueprint(P2) 진입 불가"
}
```

#### 기존 P2 entry_conditions 업데이트

기존 P2의 `entry_conditions` 에 다음을 추가한다:
```json
"05_planning/toc_draft.json 존재 및 consultant_approval = 'approved'"
```

---

### STEP 2: `orchestration/gate_rules.json` 업데이트

파일을 읽고 다음 두 게이트를 추가한다:

```json
{
  "gate_id": "GATE-P05-TO-P1",
  "name": "인테이크 완료 게이트",
  "from_phase": "P0.5",
  "to_phase": "P1",
  "auto_pass_conditions": [
    "00_definition/intake_manifest.json 존재",
    "intake_manifest.A_structure.toc_style 값이 있음",
    "intake_manifest.A_structure.scope_inclusions 비어있지 않음"
  ],
  "human_approval_required": false,
  "blocking_if_missing": ["intake_manifest.json"],
  "notes": "자동 통과. intake_manifest가 없으면 차단."
},
{
  "gate_id": "GATE-P15-TO-P2",
  "name": "목차 승인 게이트",
  "from_phase": "P1.5",
  "to_phase": "P2",
  "auto_pass_conditions": [],
  "human_approval_required": true,
  "approval_prompt": "위 목차 초안을 승인하시겠습니까? 수정 사항이 있으면 말씀해주세요.",
  "blocking_if_missing": ["toc_draft.json"],
  "notes": "반드시 컨설턴트 명시 승인 필요. P2→P3 게이트와 동급 중요도."
}
```

---

### STEP 3: `CLAUDE.md` 업데이트

CLAUDE.md를 읽고 다음 두 곳을 수정한다.

#### 수정 1: 워크플로우 파이프라인 섹션

기존:
```
P0 프로젝트 정의 → P1 자료 투입 → P2 기획(blueprint) → P3 버킷 구축
→ P4 초안 작성 → P5 검수 → P6 초안 정리·핸드오프 → P7 증거 패키지
```

변경:
```
P0 프로젝트 정의 → P0.5 인테이크 인터뷰 → P1 자료 투입 → P1.5 목차 논의
→ P2 기획(blueprint) → P3 버킷 구축 → P4 초안 작성 → P5 검수
→ P6 초안 정리·핸드오프 → P7 증거 패키지
```

그 아래 주석도 업데이트:
```
- P0.5: 인테이크 인터뷰 — intake_manifest.json 생성. 컨설턴트와 목차·스타일·포함범위 사전 확정
- P1.5: 목차 논의 — toc_draft.json 생성 및 컨설턴트 승인. P2→P3 게이트와 동급 중요도
- P2→P3 게이트가 가장 중요: 승인된 writing_blueprint 없이 초안 작성 진입 불가
```

#### 수정 2: 서브에이전트 일람 테이블

기존 테이블에 행 추가:

```
| intake-interviewer | `agents/intake-interviewer.md` | 프로젝트 인테이크 인터뷰, intake_manifest 생성 | ephemeral |
```

기존 `data-analyst` 행 설명 업데이트:
```
data-analyst | ... | 파일 투입·정규화·중복탐지·세그먼트 추출 **+ 파일처리 한계 고지 + 데이터 갭 리포트** | ephemeral
```

기존 `toc-planner` 행 설명 업데이트:
```
toc-planner | ... | 목차·구조 설계, **목차 초안 컨설턴트 승인**, writing_blueprint 생성 | persistent (per project)
```

---

### STEP 4: 업데이트 검증

다음을 확인한다:

1. `orchestration/phase_rules.json` 이 유효한 JSON인지 확인
   ```bash
   /opt/homebrew/bin/python3.13 -c "
   import json
   with open('orchestration/phase_rules.json') as f:
       data = json.load(f)
   print(f'페이즈 수: {len(data.get(\"phases\", []))}')
   "
   ```
   ※ 파일 구조에 따라 명령어를 조정한다.

2. `orchestration/gate_rules.json` 이 유효한 JSON인지 확인

3. CLAUDE.md에 "P0.5 인테이크 인터뷰"와 "P1.5 목차 논의"가 모두 포함됐는지 확인

---

## 완료 기준

1. `phase_rules.json` 에 P0.5와 P1.5가 추가됐다
2. `gate_rules.json` 에 GATE-P05-TO-P1과 GATE-P15-TO-P2가 추가됐다
3. `CLAUDE.md` 파이프라인 설명이 P0.5, P1.5를 포함한다
4. `CLAUDE.md` 서브에이전트 일람에 intake-interviewer가 추가됐다
5. 두 JSON 파일 모두 문법 오류 없음

---

## 결정 원칙

- `phase_rules.json` 과 `gate_rules.json` 의 기존 내용은 삭제하지 않는다
- `CLAUDE.md` 의 "금지 사항" 및 "일관성 계약" 섹션은 수정하지 않는다
- phase_rules.json이 배열인지 객체인지 읽기 전에 확인하고, 기존 구조를 유지한다
- gate_rules.json도 동일하게 기존 구조 확인 후 추가한다
