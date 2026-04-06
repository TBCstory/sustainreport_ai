# 점검 결과 및 수정 지시문

> 점검일: 2026-04-02
> 점검 범위: 설계 의도(CLAUDE.md) 대비 전체 구현물 전수 점검

---

## 1. CRITICAL — 런타임 동작을 차단하는 결함

### 1.1 `llm/router.py` — litellm API 호출 메서드 오류
- **위치**: `router.py:203`
- **문제**: `litellm.messages_complete()` 메서드는 존재하지 않음. litellm의 실제 API는 `litellm.completion()`
- **영향**: LLM 호출 시 `AttributeError` 발생, 모든 에이전트 실행 불가
- **수정**:
  ```python
  # AS-IS
  response = litellm.messages_complete(model=..., messages=..., ...)
  # TO-BE
  response = litellm.completion(model=..., messages=..., ...)
  ```
- **추가**: 응답 파싱도 litellm.completion의 반환 구조에 맞춰야 함. `response["choices"][0]["message"]["content"]`가 아닌 `response.choices[0].message.content` (ModelResponse 객체)

### 1.2 `llm/router.py` — `call_log.py`와의 인터페이스 불일치
- **위치**: `router.py:253`, `router.py:261-282`
- **문제**: `router.py` 내부에 `save_call_log(entry: dict)` 함수가 별도 정의되어 있고, `call_log.py`의 `save_call_log(entry: CallLogEntry)` 함수와 시그니처 충돌. 같은 이름의 함수가 두 파일에 각각 다른 스펙으로 존재
- **영향**: router.py가 call_log.py를 import하지 않고 자체 save_call_log를 사용 → call_log.py의 CallLogEntry, 비용 계산 등이 사용되지 않음
- **수정**: router.py에서 `from llm.call_log import save_call_log, CallLogEntry, calculate_cost` 사용. 내부 중복 함수 제거

### 1.3 `scripts/rebuild_summaries.py` — phase_rules.json 경로 해석 오류
- **위치**: `rebuild_summaries.py:83`
- **문제**: `workspace.parent.parent / "orchestration" / "phase_rules.json"` — workspace가 `workspaces/PRJ-YYYY-CODE-NNN`이면 `parent.parent`는 프로젝트 루트가 아님 (루트의 상위 디렉토리를 가리킴)
- **영향**: phase_rules.json을 찾지 못해 next_actions 생성 시 phase-based suggestion 실패
- **수정**: `scripts/check_gate.py`와 동일한 패턴 사용 → `Path(__file__).parent.parent / "orchestration" / "phase_rules.json"` (스크립트 위치 기준)

### 1.4 `scripts/rebuild_summaries.py` — incidents.json을 JSONL로 읽지만 실제는 JSON Array
- **위치**: `rebuild_summaries.py:93-94`
- **문제**: `read_incidents()`가 `load_jsonl()`을 사용하지만, `log_event.py`는 incidents.json을 `json.dump(list, ...)` 형태(JSON Array)로 저장함 (JSONL이 아님)
- **영향**: incidents가 전혀 읽히지 않아 incident 기반 blocking issue가 누락됨
- **수정**: `read_incidents()`에서 `load_json()` 사용 후 list 반환

---

## 2. HIGH — 설계 의도 위반 또는 기능 결함

### 2.1 에이전트 프롬프트 — 혼합 언어 오염 (중국어/일본어)
- **영향 파일 및 위치**:
  - `agents/data-analyst.md:9` — `###不是什么` (중국어 "무엇이 아닌가")
  - `agents/fact-checker.md:7` — `外部 公言事項` (중국어/일본어 혼합)
  - `agents/fact-checker.md:13` — `섹션 내矛盾 탐지` (중국어)
  - `agents/fact-checker.md:156` — `과거也无参照` (중국어)
  - `orchestration/agent_contracts.json:186` — `파일血缘` (중국어)
  - `orchestration/agent_contracts.json:197` — `証拠...断裂` (일본어/중국어)
  - `orchestration/agent_runtime_policy.json:9` — `전生命周期を通じて` (일본어)
  - `orchestration/agent_runtime_policy.json:71` — `P3-P5を通じて待机` (일본어)
  - `orchestration/model_routing.json:12` — `provider_config参照` (중국어)
  - `llm/router.py:124` — `poc_mode 설정优先` (중국어)
- **수정**: 모든 혼합 언어를 한국어로 교정. `.claude/agents/`도 동일하게 반영
  - `不是什么` → `하지 않는 것`
  - `外部 公言事項` → `외부 공시 사항`
  - `矛盾` → `모순`
  - `血缘` → `혈통(lineage)`
  - `証拠` → `증거`, `断裂` → `단절`
  - `生命周期を通じて` → `생명주기 동안`
  - `待机` → `대기`
  - `参照` → `참조`
  - `优先` → `우선`

### 2.2 `agents/provenance-builder.md` — guidance 파일 참조 누락
- **문제**: CLAUDE.md "모든 서브에이전트가 작업 전에 반드시 참조해야 하는 파일" 규칙 위반. provenance-builder의 입력 계약에 `guidance/style_guide.json`, `guidance/terminology_dictionary.json`, `guidance/writing_blueprint.json` 없음
- **수정**: 입력 계약 테이블에 3개 guidance 파일을 `선택` 또는 `필수`로 추가

### 2.3 `agents/framework-mapper.md` — writing_blueprint 참조 누락
- **문제**: `writing_blueprint.json` 참조 없음 (style_guide는 참조하지만 blueprint는 미참조)
- **수정**: 입력 계약에 `guidance/writing_blueprint.json` 추가 (선택, 섹션별 깊이 참조용)

### 2.4 `orchestration/agent_contracts.json` — provenance-builder 출력 스키마 불일치
- **위치**: line 192
- **문제**: 두 번째 output_contracts 항목이 `"description"` 대신 `"purpose"` 키 사용
- **수정**: `"purpose"` → `"description"`으로 통일

### 2.5 `orchestration/gate_rules.json` — P5_to_P6 required_approvers 혼동
- **위치**: line 24
- **문제**: `required_approvers: ["fact_checker", "internal_reviewer"]` — 에이전트 역할명을 사람 승인자로 기재. `approval_type: "human"` 인데 에이전트 이름이 들어감
- **수정**: `["consultant_lead", "quality_reviewer"]` 등 사람 역할명으로 변경하거나, 에이전트가 생성한 리포트의 auto-check를 의미하는 것이면 `approval_type`을 `"semi-auto"`로 변경하고 주석 추가

### 2.6 `orchestration/gate_rules.json` — auto_gate에 P4→P5 누락
- **위치**: line 38
- **문제**: description에 "P0→P1, P1→P2, P3→P4, P6→P7" 나열하지만 **P4→P5 언급 없음**
- **수정**: description에 P4→P5 추가. 더 나아가, `applies_to` 배열을 machine-readable로 추가:
  ```json
  "applies_to": ["P0_to_P1", "P1_to_P2", "P3_to_P4", "P4_to_P5", "P6_to_P7"]
  ```

### 2.7 `scripts/init_workspace.py` — `manual_overrides.json` 미생성
- **문제**: CLAUDE.md 워크스페이스 구조에 `manual_overrides.json`이 명시되어 있으나 init_workspace.py가 생성하지 않음
- **수정**: `_make_initial_json` 패턴으로 `manual_overrides.json` 생성 추가 (`{"overrides": []}`)

### 2.8 `scripts/init_workspace.py` — CLI 프레임워크 불일치
- **문제**: 다른 5개 스크립트는 모두 click 사용하지만, init_workspace.py만 argparse 사용
- **수정**: click으로 통일 (선택적이나, 일관성 위반)

### 2.9 `orchestration/phase_rules.json` — gate_id 교차 참조 누락
- **문제**: `gate_required: true`인 P2, P5에 `gate_id` 필드가 없어 check_gate.py와의 machine-readable 연결 부재. 현재 check_gate.py가 하드코딩으로 P2_to_P3, P5_to_P6를 처리함
- **수정**: P2에 `"gate_id": "P2_to_P3"`, P5에 `"gate_id": "P5_to_P6"` 추가

---

## 3. MEDIUM — 정합성·품질 이슈

### 3.1 `orchestration/agent_runtime_policy.json` — provenance-builder 페이즈 불일치
- **문제**: lifecycle.start가 `"P6 단계에서"` 시작으로 기술. CLAUDE.md는 provenance-builder를 P7에 배정
- **수정**: `"P7 단계에서 증거 패키지 조립 시작"` 또는, P6 핸드오프에서 일부 선행 작업을 하는 것이 의도라면 CLAUDE.md와 함께 정리

### 3.2 `orchestration/agent_runtime_policy.json` — toc-planner 스코프 초과
- **문제**: lifecycle.end가 `"P3-P5を通じて待机"` — CLAUDE.md는 toc-planner를 P2에 배정하지만 P3-P5까지 대기 상태 유지
- **수정**: 설계 의도 확인 필요. blueprint 수정 요청 시 재활성화가 목적이면 그 사유를 명시적으로 기록

### 3.3 `llm/router.py` — run_id 생성 코드 중복
- **문제**: `generate_run_id()` 함수가 `log_event.py`와 `router.py`에 각각 독립 구현. 시퀀스 파일(`/tmp/.sustainreport_run_seq_`)을 공유하지만 로직이 미묘하게 다름 (log_event.py는 `current[1]`, router.py는 `current[1:]`)
- **수정**: 공유 유틸리티 모듈로 추출 (예: `scripts/utils.py` 또는 `llm/utils.py`)

### 3.4 `llm/call_log.py` — CONTEXT_BUS_DIR 상대경로 고정
- **위치**: line 33
- **문제**: `CONTEXT_BUS_DIR = Path("context_bus")` — 현재 작업 디렉토리가 workspace가 아니면 잘못된 경로
- **수정**: workspace 경로를 매개변수로 받도록 변경

### 3.5 스키마 — section_id 패턴 불일치
- **문제**: `structure_index.schema.json`은 section_id 패턴이 `^(SEC-\\d+(\\.\\d+)*|SUB-SEC-\\d+(\\.\\d+)*-[A-Z])$`인 반면, `writing_blueprint.schema.json`은 `^SEC-\\d+(\\.\\d+)*$`만 허용. SUB-SEC 패턴이 blueprint에서 배제됨
- **수정**: writing_blueprint에서도 SUB-SEC 처리 여부 결정. 사용하지 않는다면 structure_index에서만 SUB-SEC 허용이 맞고, 사용한다면 blueprint에도 추가

### 3.6 `scripts/normalize.py` — segment_id가 파일 단위 리셋
- **위치**: `normalize.py:109`
- **문제**: `segment_id = f"SEG-{segment_num:05d}"` — 파일마다 SEG-00001부터 시작. 여러 파일을 변환하면 segment_id가 충돌
- **수정**: workspace 레벨의 글로벌 카운터 도입 (file_id의 next_file_id.json 패턴과 동일하게)

### 3.7 `scripts/normalize.py` — metadata에서 page_count에 tables_detected 할당
- **위치**: `normalize.py:275`
- **문제**: `"page_count": metadata.get("tables_detected", 0)` — 테이블 수를 페이지 수로 잘못 할당
- **수정**: `"page_count": None` 또는 별도 로직으로 페이지 수 추출

### 3.8 `.claude/agents/` — agents/와 내용 중복이지만 어댑터 역할 불명확
- **문제**: `.claude/agents/*.md`가 `agents/*.md`의 거의 전체 내용을 복사. CLAUDE.md의 "agents/를 참조하는 래퍼" 의도와 달리 독립 복사본
- **영향**: 수정 시 양쪽 모두 갱신해야 하는 동기화 부담
- **수정**: `.claude/agents/*.md`를 진짜 래퍼로 변경 — agents/*.md를 `Read`로 참조하도록 지시하는 짧은 어댑터로 축소. 예:
  ```markdown
  # section-writer
  ## Description
  증거 기반 섹션 초안 작성 에이전트
  ## Instructions
  이 에이전트의 전체 프롬프트는 `agents/section-writer.md`에 있습니다.
  반드시 해당 파일을 읽고 그 지시를 따르세요.
  ```

---

## 4. LOW — 개선 권장

### 4.1 `pyproject.toml` — 의존성 설치 미완료
- litellm, markitdown, click, rich 등이 실제 환경에 설치되어 있지 않음
- `uv sync` 실행 필요

### 4.2 `scripts/check_gate.py` — phase_rules의 complex exit condition type 미처리
- `review_complete`, `handoff_package_complete`, `evidence_pack_complete` 타입의 exit_conditions가 단순 file_exists fallback으로 처리됨
- 향후 각 타입별 전용 체크 로직 필요

### 4.3 `guidance/style_guide.json`, `guidance/terminology_dictionary.json` — 프로젝트 루트에만 존재
- workspace 내 `guidance/` 디렉토리에도 복사되어야 에이전트가 workspace 기준으로 접근 가능
- init_workspace.py에서 기본 템플릿을 guidance/에 복사하는 로직 추가 권장

### 4.4 테스트 부재
- 스크립트, LLM 래퍼, 게이트 판정 로직에 대한 unit test 없음
- `tests/` 디렉토리 및 pytest 설정 필요

### 4.5 `templates/framework_db/` — 프레임워크 DB 검증 미실시
- 5개 프레임워크 DB의 disclosure ID가 에이전트 프롬프트에서 참조하는 형식과 일치하는지 미검증

---

## 수정 우선순위 요약

| 순서 | ID | 심각도 | 작업량 | 내용 |
|------|----|--------|--------|------|
| 1 | 1.1 | CRITICAL | S | router.py litellm API 수정 |
| 2 | 1.2 | CRITICAL | M | router.py ↔ call_log.py 인터페이스 통합 |
| 3 | 1.3 | CRITICAL | S | rebuild_summaries.py 경로 수정 |
| 4 | 1.4 | CRITICAL | S | rebuild_summaries.py incidents 읽기 수정 |
| 5 | 2.1 | HIGH | M | 혼합 언어 전수 교정 (10+ 파일) |
| 6 | 2.2-2.3 | HIGH | S | 에이전트 guidance 참조 추가 |
| 7 | 2.4-2.6 | HIGH | S | orchestration JSON 정합성 수정 |
| 8 | 2.7 | HIGH | S | init_workspace manual_overrides 추가 |
| 9 | 2.9 | HIGH | S | phase_rules gate_id 추가 |
| 10 | 3.6 | MEDIUM | M | normalize.py segment_id 글로벌 카운터 |
| 11 | 3.7 | MEDIUM | S | normalize.py page_count 수정 |
| 12 | 3.3 | MEDIUM | M | run_id 생성 코드 통합 |
| 13 | 3.8 | MEDIUM | L | .claude/agents/ 래퍼 구조 변경 |
| 14 | 2.8 | HIGH | S | init_workspace click 통일 (선택) |
| 15 | 4.1-4.5 | LOW | L | 환경설정, 테스트, 검증 |

> **S** = 10분 이내, **M** = 30분 이내, **L** = 1시간+

---

## 다음 세션 실행 순서 제안

```
세션 A: Critical 수정 (1.1 → 1.2 → 1.3 → 1.4)
세션 B: 혼합 언어 교정 + guidance 참조 보완 (2.1 → 2.2 → 2.3)
세션 C: Orchestration 정합성 + init_workspace (2.4 → 2.9 → 2.7)
세션 D: normalize.py 수정 + run_id 통합 (3.6 → 3.7 → 3.3)
세션 E: .claude/agents/ 래퍼 리팩토링 (3.8)
세션 F: 테스트 작성 + uv sync (4.1 → 4.4)
```
