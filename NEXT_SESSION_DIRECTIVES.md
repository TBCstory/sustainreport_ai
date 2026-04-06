# Session #9 — 수정 실행 지시문

**생성일:** Session #8 종료 시  
**병합 출처:** `AUDIT_DIRECTIVES.md` (사용자 검토) + `AUDIT_CHECKLIST.md` (병렬 감사)  
**상태:** 🔴 미수행

---

## 🔴 CRITICAL — 즉시 수정 필요 (런타임 오류/데이터 무결성)

### [CR-1] `llm/router.py` — `litellm.completion()` 오류 (runtime crash)
- **위치:** `router.py:203`
- **문제:** `litellm.messages_complete()` 메서드는 존재하지 않음 → `AttributeError`로 모든 에이전트 실행 불가
- **수정:**
  ```python
  # AS-IS
  response = litellm.messages_complete(model=..., messages=..., ...)
  # TO-BE
  response = litellm.completion(model=..., messages=..., ...)
  ```
- **추가:** `response["choices"][0]["message"]["content"]` → `response.choices[0].message.content` (ModelResponse 객체)
- **출처:** AUDIT_DIRECTIVES.md §1.1

### [CR-2] `llm/router.py` — `save_call_log` 중복 정의 충돌
- **위치:** `router.py:253`, `router.py:261–282`
- **문제:** `router.py` 내부 `save_call_log(entry: dict)`와 `call_log.py`의 `save_call_log(entry: CallLogEntry)` 시그니처 충돌. `call_log.py`의 비용 계산·구조화 로직이 무시됨
- **수정:** `router.py`에서 `from llm.call_log import save_call_log, CallLogEntry, calculate_cost` import. 내부 중복 함수 제거
- **출처:** AUDIT_DIRECTIVES.md §1.2

### [CR-3] `scripts/rebuild_summaries.py` — phase_rules.json 경로 오류
- **위치:** `rebuild_summaries.py:83`
- **문제:** `workspace.parent.parent / "orchestration" / "phase_rules.json"` — workspace가 `workspaces/PRJ-YYYY-CODE-NNN`일 때 `parent.parent`는 프로젝트 루트의 상위 디렉토리
- **수정:** `Path(__file__).parent.parent / "orchestration" / "phase_rules.json"`로 변경 (스크립트 기준 절대경로)
- **출처:** AUDIT_DIRECTIVES.md §1.3

### [CR-4] `scripts/rebuild_summaries.py` — incidents.json JSON vs JSONL 불일치
- **위치:** `rebuild_summaries.py:93–94` (`read_incidents()`)
- **문제:** `load_jsonl()` 사용하지만 `log_event.py`는 `json.dump(list, ...)` (JSON Array)로 저장 → incidents가 전무 읽힘
- **수정:** `read_incidents()`를 `load_json()` 사용 후 list 반환으로 변경
- **출처:** AUDIT_DIRECTIVES.md §1.4

### [CR-5] `templates/framework_db/tcfd_db.json` — G4 incomplete string
- **위치:** TCFD G4 `recommended_metrics` 중
- **문제:** `" istrumen"` 트렁케이션 (문자열中途切断)
- **수정:** G4 `recommended_metrics` 전체 재입력 또는 원본 출처 확인 후 수정
- **출처:** AUDIT_CHECKLIST.md §5.1

### [CR-6] `templates/framework_db/kssb_db.json` — Chinese characters 혼입
- **문제:** `disclosure_requirements`에 `温室가스`, `的员工数`, `强迫노동` 등 Chinese 혼입
- **수정:** 한국어로 전량 교체 — `탄소가스`, `총직원수`, `강제노동` 등
- **출처:** AUDIT_CHECKLIST.md §5.2

### [CR-7] `guidance/style_guide.json` — corrupted mixed-script field
- **위치:** `numeric_expression` 필드
- **문제:** `"阿拉伯数字優先 (수치는 숫자, 단위: tCO2e, GWh 등)"` — Chinese/Japanese 혼입
- **수정:** `"수치: 숫자 사용, 단위: tCO2e, GWh 등"`로 교체
- **출처:** AUDIT_CHECKLIST.md §6.1

### [CR-8] `scripts/init_workspace.py` — `manual_overrides.json` 미생성
- **문제:** CLAUDE.md 워크스페이스 구조에 명시된 `manual_overrides.json` 미생성
- **수정:** `_make_initial_json()` 패턴으로 `manual_overrides.json` 생성 (`{"overrides": []}`)
- **출처:** AUDIT_DIRECTIVES.md §2.7

---

## 🟡 HIGH — 설계 의도 위반 / 기능 결함

### [HI-1] 혼합 언어 오염 일괄 교정
- **대상 파일 (10+):**
  - `agents/data-analyst.md:9` — `不是什么` → `하지 않는 것`
  - `agents/fact-checker.md:7` — `外部 公言事項` → `외부 공시 사항`
  - `agents/fact-checker.md:13` — `섹션 내矛盾 탐지` → `섹션 내 모순 탐지`
  - `agents/fact-checker.md:156` — `과거也无参照` → `과거 참조 없음`
  - `orchestration/agent_contracts.json:186` — `파일血缘` → `파일 혈통(lineage)`
  - `orchestration/agent_contracts.json:197` — `証拠...断裂` → `증거...단절`
  - `orchestration/agent_runtime_policy.json:9` — `전生命周期を通じて` → `생명주기 동안`
  - `orchestration/agent_runtime_policy.json:71` — `P3-P5ozilla待机` → `P3-P5 대기`
  - `orchestration/model_routing.json:12` — `provider_config参照` → `provider_config 참조`
  - `llm/router.py:124` — `poc_mode 설정优先` → `poc_mode 설정 우선`
- **출처:** AUDIT_DIRECTIVES.md §2.1 + AUDIT_CHECKLIST.md cross-cutting

### [HI-2] `orchestration/agent_runtime_policy.json` — provenance-builder phase 불일치
- **문제:** lifecycle.start이 `"P6 단계에서"` — CLAUDE.md와 phase_rules.json은 P7 배정
- **수정:** `"P7 단계에서 증거 패키지 조립 시작"`로 교정
- **출처:** AUDIT_CHECKLIST.md §1.1 + AUDIT_DIRECTIVES.md §3.1

### [HI-3] `orchestration/gate_rules.json` — P5_to_P06 required_approvers 불일치
- **문제:** `required_approvers: ["fact_checker", "internal_reviewer"]` — human approval에 agent 이름 부적합
- **수정:** human 역할명(`["consultant_lead", "quality_reviewer"]`) 또는 `approval_type`을 semi-auto로 변경
- **출처:** AUDIT_DIRECTIVES.md §2.5

### [HI-4] `orchestration/gate_rules.json` — auto_gate P4→P5 누락
- **문제:** description에 P4→P5 미기재
- **수정:** description 수정 + `applies_to` 배열 추가:
  ```json
  "applies_to": ["P0_to_P1", "P1_to_P2", "P3_to_P4", "P4_to_P5", "P6_to_P7"]
  ```
- **출처:** AUDIT_DIRECTIVES.md §2.6

### [HI-5] `orchestration/phase_rules.json` — gate_id 교차 참조 누락
- **문제:** P2, P5에 `gate_id` 필드 없음 → check_gate.py와 machine-readable 연결 부재
- **수정:** P2에 `"gate_id": "P2_to_P3"`, P5에 `"gate_id": "P5_to_P6"` 추가
- **출처:** AUDIT_DIRECTIVES.md §2.9

### [HI-6] Agent guidance 파일 참조 누락
| Agent | 파일 | 수정 | 출처 |
|-------|------|------|------|
| `internal-reviewer` | `agents/`, `.claude/agents/` | 3개 guidance 파일 모두 input contracts에 **필수** 추가 | AUDIT_CHECKLIST §3.1 |
| `fact-checker` | `agents/`, `.claude/agents/` | `style_guide`, `terminology_dictionary` "필요시" → **"필수"** | AUDIT_DIRECTIVES §2.2 |
| `provenance-builder` | `agents/`, `.claude/agents/` | 3개 guidance 파일 input contracts 추가 | AUDIT_DIRECTIVES §2.2 |
| `toc-planner` | `agents/`, `.claude/agents/` | `writing_blueprint.json` input contracts 추가 (재진입 시 필요) | AUDIT_CHECKLIST §3.5 |

### [HI-7] `agents/data-analyst.md` — `.claude/agents/`에 hallucination 방지 조항 누락
- **문제:** `agents/data-analyst.md`의 "출처 없는 메타데이터 추정 금지" 조항이 `.claude/agents/data-analyst.md`에缺失
- **수정:** `.claude/agents/data-analyst.md`의 `## 금지的事项`에 해당 조항 추가
- **출처:** AUDIT_CHECKLIST.md §3.2

### [HI-8] `orchestration/agent_contracts.json` — provenance-builder output 스키마 불일치
- **문제:** output 두 번째 항목이 `"description"` 대신 `"purpose"` 키 사용
- **수정:** `"purpose"` → `"description"` 통일
- **출처:** AUDIT_DIRECTIVES.md §2.4

### [HI-9] `scripts/check_gate.py` — entry_conditions 검증 부재
- **문제:** phase_rules.json의 entry_conditions 정의되어 있으나 검증 로직 없음
- **수정:** `_check_entry_conditions()` 함수 구현
- **출처:** AUDIT_CHECKLIST.md §2.1 + §7.3

### [HI-10] `scripts/update_project_state.py` — `len() > 0` phase 판단 오류
- **문제:** `_all_bucket_files_exist()`, `_all_draft_meta_files_exist()`가 any 파일 존재만 확인
- **수정:** SEG-NNNNN 매니페스트 읽어서 전체 required 파일 목록 존재 확인
- **출처:** AUDIT_CHECKLIST.md §2.2

### [HI-11] `scripts/log_event.py` — `run_id` event record 미포함
- **문제:** `log_gate_blocked()`, `log_incident()`가 `run_id`를 return하지만 event dict에 미포함
- **수정:** 두 함수에서 `"run_id": run_id` event dict에 추가
- **출처:** AUDIT_CHECKLIST.md §2.3

---

## 🟡 MEDIUM — 정합성 / 품질

### [ME-1] `scripts/normalize.py` — segment_id 파일 단위 리셋
- **문제:** `segment_num:05d` 파일마다 1부터 시작 → 충돌
- **수정:** workspace 레벨 글로벌 카운터 도입 (`next_file_id.json` 패턴 동일하게)
- **출처:** AUDIT_DIRECTIVES.md §3.6

### [ME-2] `scripts/normalize.py` — `page_count` 잘못 할당
- **문제:** `"page_count": metadata.get("tables_detected", 0)` — 테이블 수를 페이지 수로 할당
- **수정:** `page_count: None` 또는 별도 페이지 수 추출 로직
- **출처:** AUDIT_DIRECTIVES.md §3.7

### [ME-3] `llm/router.py` — `generate_run_id()` 중복 구현
- **문제:** `log_event.py`와 `router.py`에 각각 독립 구현, 시퀀스 파일 충돌 가능
- **수정:** 공유 유틸리티 모듈 추출 (예: `scripts/utils.py`)
- **출처:** AUDIT_DIRECTIVES.md §3.3

### [ME-4] `scripts/init_workspace.py` — argparse vs click 불일치
- **문제:** 나머지 5개 스크립트는 click, init_workspace.py만 argparse
- **수정:** click으로 통일 (선택적 — 일관성 목적)
- **출처:** AUDIT_DIRECTIVES.md §2.8

### [ME-5] `.claude/agents/` — 독립 복사본而非 래퍼
- **문제:** `agents/*.md` 내용을 그대로 복사. 수정 시 양쪽 동기화 부담
- **수정:** 진짜 래퍼로 변경 — 전체 프롬프트를 `agents/*.md`에서 Read하도록 지시하는 짧은 어댑터로 축소
- **출처:** AUDIT_DIRECTIVES.md §3.8

### [ME-6] `schemas/draft_queries.schema.json` — `dq_id` 패턴 불일치
- **문제:** `^DQ-\\d{3}$` (3자리固定) vs CLAUDE.md `DQ-NNN`
- **수정:** `^DQ-\\d{1,3}$` 또는 leading zero 정책 명시
- **출처:** AUDIT_CHECKLIST.md §4.1

### [ME-7] `schemas/framework_index.schema.json` — `KSSB_S2` underscore 불일치
- **문제:** `KSSB_S2` (underscore) vs 다른 schema `KSSB` 불일치
- **수정:** KSSB 표준 명칭 확인 후 통일
- **출처:** AUDIT_CHECKLIST.md §4.2

### [ME-8] `templates/framework_db/esrs_db.json` — whitespace 불일치
- **문제:** `data_point` 배열 선행/후행 공백 불일치 (예: `" 기후변화 관련 전략"` 선행 공백)
- **수정:** 모든 `data_point` 문자열 `.strip()` 후 재저장
- **출처:** AUDIT_CHECKLIST.md §5.3

### [ME-9] `guidance/terminology_dictionary.json` — `Scope 3` 오타
- **문제:** `"기타 간실 온실가스 배출량"` → `"기타 간접 온실가스 배출량"` (간실→간접)
- **수정:** 해당 값 수정
- **출처:** AUDIT_CHECKLIST.md §6.2

### [ME-10] `scripts/rebuild_summaries.py` — `generate_next_actions()` 미활용
- **문제:** `phase_rules` 파라미터 받지만 `current_phase`, `next_phase`만 사용
- **수정:** exit_conditions 기반 스마트 next action 생성 로직 보강
- **출처:** AUDIT_CHECKLIST.md §2.6

---

## 🟡 LOW — 개선 권장

| ID | 파일 | 이슈 | 출처 |
|----|------|------|------|
| LO-1 | `pyproject.toml` | 의존성 미설치 (`uv sync` 미실행) | AUDIT_DIRECTIVES.md §4.1 |
| LO-2 | `scripts/check_gate.py` | `review_complete` 등 complex exit condition type 미처리 | AUDIT_CHECKLIST §2.10 |
| LO-3 | `guidance/` | workspace 내 `guidance/` 복사 로직 부재 | AUDIT_DIRECTIVES.md §4.3 |
| LO-4 | `tests/` | unit test 부재 | AUDIT_DIRECTIVES.md §4.4 |
| LO-5 | `templates/framework_db/` | disclosure ID 포맷 미검증 | AUDIT_DIRECTIVES.md §4.5 |
| LO-6 | `schemas/file_registry.schema.json` | root level `title` 필드 누락 | AUDIT_CHECKLIST §4.3 |
| LO-7 | `schemas/*.schema.json` | `phase` enum P0-P7 constraint 부재 | AUDIT_CHECKLIST §4.4 |
| LO-8 | `llm/router.py` | `generate_run_id()` `/tmp` concurrent 충돌 가능 | AUDIT_CHECKLIST §2.12 |
| LO-9 | `guidance/terminology_dictionary.json` | `RE100` 항목 `usage` 필드 누락 | AUDIT_CHECKLIST §6.3 |

---

## 실행 순서 (세션 #9)

```
[CR-1 → CR-2 → CR-3 → CR-4]  → Runtime crash 4종 수정
     ↓
[CR-5 → CR-6 → CR-7 → CR-8]  →  Data integrity 4종 수정
     ↓
[HI-1]                       →  Mixed-language 교정 (10+ 파일)
     ↓
[HI-2 → HI-3 → HI-4 → HI-5] →  Orchestration 정합성
     ↓
[HI-6 → HI-7 → HI-8]        →  Agent 계약/프롬프트
     ↓
[HI-9 → HI-10 → HI-11]      →  Python 스크립트 로직
     ↓
[ME-1 → ME-2 → ME-3 → ME-4]  →  Medium priority
     ↓
[LO-1 → LO-2 → LO-3 → LO-4 → LO-5]  →  Environment + tests
```

---

## 수정 후 검증 체크리스트

- [ ] `python3.13 -c "from llm.router import ModelRouter; r = ModelRouter(); print(r.list_models())"` — 오류 없이 실행
- [ ] `python3.13 scripts/check_gate.py --workspace workspaces/PRJ-2026-TST-001 --from P1 --to P2` — phase_rules 로드 성공
- [ ] `python3.13 scripts/rebuild_summaries.py --workspace workspaces/PRJ-2026-TST-001` — incidents.json 읽기 성공
- [ ] `python3.13 scripts/init_workspace.py --project-id PRJ-2026-TST-003` — manual_overrides.json 생성 확인
- [ ] `grep -r "证据\|温室\|也无\|血缘\|参照\|优先\|待机" orchestration/ agents/ .claude/agents/` — 0 results
- [ ] `python3.13 -c "import json; [json.load(open(f)) for f in ['templates/framework_db/tcfd_db.json','templates/framework_db/kssb_db.json','guidance/style_guide.json']]"` — JSON 유효성

---

## 출처 비교표

| ID | AUDIT_DIRECTIVES.md | AUDIT_CHECKLIST.md | 비고 |
|----|---------------------|---------------------|------|
| CR-1 | §1.1 | — | router.py API |
| CR-2 | §1.2 | — | router.py vs call_log.py |
| CR-3 | §1.3 | — | rebuild_summaries 경로 |
| CR-4 | §1.4 | — | rebuild_summaries JSONL |
| CR-5 | — | §5.1 | TCFD G4 truncation |
| CR-6 | — | §5.2 | KSSB Chinese chars |
| CR-7 | — | §6.1 | style_guide corruption |
| CR-8 | §2.7 | — | manual_overrides 미생성 |
| HI-1 | §2.1 | cross-cutting | Mixed language (10+ files) |
| HI-2 | §3.1 | §1.1 | provenance-builder phase |
| HI-3 | §2.5 | — | gate_rules approvers |
| HI-4 | §2.6 | — | auto_gate P4→P5 |
| HI-5 | §2.9 | — | phase_rules gate_id |
| HI-6 | §2.2-2.3 | §3.1, §3.4, §3.5 | Agent guidance refs |
| HI-7 | — | §3.2 | data-analyst hallucination |
| HI-8 | §2.4 | — | agent_contracts schema |
| HI-9 | — | §2.1, §7.3 | check_gate entry_conditions |
| HI-10 | — | §2.2 | update_project_state len>0 |
| HI-11 | — | §2.3 | log_event run_id |