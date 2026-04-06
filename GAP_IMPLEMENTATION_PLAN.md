# Session #20 구현 계획 — 파이프라인 실행 엔진 구축

**작성일:** Session #19 완료 후  
**목적:** 오케스트레이션 시스템의 핵심 결함인 **파이프라인 실행 엔진** 및 **에이전트 디스패치 시스템**을 구현하여 End-to-End 자동화 달성

---

## 1. 현재 상태 평가

### 완료된 인프라 (Sessions #1-19)
| 컴포넌트 | 상태 | 비고 |
|---------|------|------|
| 오케스트레이션 규칙 | ✅ 완성 | `orchestration/*.json` 5개 |
| 에이전트 프롬프트 | ✅ 완성 | `agents/*.md` 7개 |
| JSON Schema | ✅ 완성 | `schemas/*.schema.json` 8개 |
| LLM 라우터 | ✅ 완성 | `llm/router.py` + `call_log.py` |
| 게이트 판정 | ✅ 완성 | `scripts/check_gate.py` |
| 상태 관리 스크립트 | ✅ 완성 | `update_project_state.py` 등 |
| 테스트 스위트 | ✅ 완성 | TC-1~TC-8 (8/8 통과) |

### 부재 판명: 실행 엔진
| 없는 것 | 영향 |
|---------|------|
| `scripts/run_pipeline.py` | Phase 순차 실행, 상태 추적, 전환 로직 없음 |
| `scripts/dispatch_agent.py` | 에이전트 프롬프트 로드 + LLM 호출 + 출력 쓰기 없음 |
| `scripts/state_manager.py` | Phase 상태 추적, 게이트 대기 로직 없음 |
| Phase별 실행 래퍼 | 각 에이전트를 호출하는 스크립트 없음 |

**핵심 문제:** 선언적 정의(what to do)는完备하지만 **명령적 실행(how to run)**이不存在.

---

## 2. 구현 전략

### 2.1 핵심 원칙
1. **パイプライン first** — 단일 명령으로 P0→P7 전체 실행 가능한 엔진 구축
2. **에이전트 디스패치 추상화** — `dispatch_agent.py`가 모든 에이전트 호출을统一 처리
3. **상태 추적** — `state_manager.py`가 Phase 전환과 Blocking Issue를 관리
4. **게이트 준수** — `check_gate.py`를 파이프라인 진행 판단의 유일한 정보원으로 사용
5. **점진적 구현** — 단위 테스트 통과 후 다음 모듈로 진행

### 2.2 모듈 의존성
```
state_manager.py       ← 프로젝트 상태 추적 (의존성 없음, 기초)
       ↓
dispatch_agent.py      ← 에이전트 호출 추상화 (state_manager 사용)
       ↓
Phase 실행 래퍼들       ← 각 Phase 에이전트 호출 (dispatch_agent 사용)
       ↓
run_pipeline.py        ← 전체 파이프라인 조율 (모든 모듈 사용)
```

---

## 3. 구현 상세

### 3.1 `scripts/state_manager.py` [Session #20-A]

**역할:** 프로젝트별 Phase 상태 추적, 전환 로직, Blocking Issue 관리

```python
# 핵심 기능
class StateManager:
    def __init__(self, workspace: str)
    
    # Phase 관리
    def get_current_phase(self) -> str
    def advance_phase(self, from_phase: str, to_phase: str) -> bool
    def is_phase_complete(self, phase: str) -> bool
    
    # Blocking Issue 관리
    def add_blocking_issue(self, issue: dict) -> str  # returns issue_id
    def resolve_blocking_issue(self, issue_id: str) -> bool
    def get_blocking_issues(self) -> list[dict]
    
    # 게이트 연동
    def requires_approval(self, gate_name: str) -> bool
    def record_approval(self, gate_name: str, approver: str, signature: str) -> bool
    
    # 상태 파일 갱신
    def sync(self) -> None  # project_state.json, blocking_issues.json 갱신
```

**상태 파일 동기화 규칙:**
- Phase 완료 시 → `project_state.json`의 `current_phase` 갱신
- Blocking Issue 발생 시 → `blocking_issues.json`에 추가 + `project_state.json`의 `issues` 반영
- 게이트 승인 기록 → `approval_gates.json`에 추가

**테스트:** `tests/test_state_manager.py` — Phase 전환, Blocking Issue 추가/해결, 승인 기록

---

### 3.2 `scripts/dispatch_agent.py` [Session #20-B]

**역할:** 에이전트 프롬프트 로드, 컨텍스트 조립, LLM 호출, 출력 파일 쓰기를统一处理

```python
# 핵심 기능
class AgentDispatcher:
    def __init__(self, workspace: str, state_manager: StateManager)
    
    def dispatch(
        self,
        agent: str,                    # "data-analyst", "toc-planner" 등
        context: dict,                # {"key": "value"} 추가 컨텍스트
        output_files: list[str],      # 생성해야 할 파일 경로
        wait_for_approval: bool = False  # 게이트 승인 대기 여부
    ) -> DispatchResult
    
    # 내부 메서드
    def _load_agent_prompt(self, agent: str) -> str
    def _build_context(self, agent: str, context: dict) -> str
    def _call_llm(self, prompt: str, agent: str) -> LLMResult
    def _write_outputs(self, result: LLMResult, output_files: list[str]) -> bool
    def _wait_for_human_approval(self, gate_name: str) -> bool
```

**에이전트 프롬프트 로드 규칙:**
1. `agents/{agent}.md` 파일을 읽음
2. `{workspace}` 플레이스홀더를 실제 워크스페이스 경로로 치환
3. `context_bus/events.jsonl`에서 최근 관련 이벤트를 로드하여 프롬프트 끝에 추가

**LLM 호출 규칙:**
- `llm/router.py`의 `ModelRouter.complete_messages()` 사용
- `agent` 필드 전달 → `call_log.jsonl`에 올바른 에이전트명 기록
- 예외 발생 시 `state_manager.add_blocking_issue()` 호출 후 재시도 또는 중단

**출력 쓰기 규칙:**
- LLM 결과의 `content`를 각 `output_files`에 쓰기
- 디렉토리가 없으면 자동 생성
- 파일 작성 완료 후 `state_manager.sync()` 호출

**테스트:** `tests/test_dispatch_agent.py` — 프롬프트 로드, 컨텍스트 조립, 출력 쓰기 검증

---

### 3.3 Phase 실행 래퍼 [Session #20-C]

각 Phase의 에이전트를 호출하는專用 스크립트. **모두 `dispatch_agent.py` 위에 구축**.

#### `scripts/run_ingestion.py` — P1
```python
def run_ingestion(workspace: str, file_paths: list[str]) -> dict:
    """
    1. 각 파일을 정규화 Markdown으로 변환 (markitdown)
    2. 세그먼트 추출
    3. file_registry.json 갱신
    4. segment_manifest.json 갱신
    """
```

#### `scripts/run_toc_planner.py` — P2
```python
def run_toc_planner(workspace: str) -> dict:
    """
    1. data-analyst 출력 (segment_manifest.json) 읽기
    2. toc-planner 에이전트 호출
    3. structure_index.json, section_manifest.json, writing_blueprint.json 생성
    4. 게이트 대기 (P2→P3 승인 필요)
    """
```

#### `scripts/run_framework_mapper.py` — P3
```python
def run_framework_mapper(workspace: str) -> dict:
    """
    1. toc-planner 출력 (writing_blueprint, structure_index) 읽기
    2. framework-mapper 에이전트 호출
    3. 06_buckets/SEC-*.json 생성
    4. framework_index.json 생성
    """
```

#### `scripts/run_section_writer.py` — P4
```python
def run_section_writer(workspace: str, section_ids: list[str] = None) -> dict:
    """
    1. framework_mapper 출력 (버킷) 읽기
    2. section-writer 에이전트 호출 (섹션별 병렬 가능)
    3. 07_drafts/SEC-*.md + SEC-*_meta.json 생성
    """
```

#### `scripts/run_internal_reviewer.py` — P5 (내부 검수)
```python
def run_internal_reviewer(workspace: str) -> dict:
    """
    1. section_writer 출력 (초안) 읽기
    2. internal-reviewer 에이전트 호출
    3. 08_review/internal_review_report.json 생성
    """
```

#### `scripts/run_fact_checker.py` — P5 (외부 검증)
```python
def run_fact_checker(workspace: str) -> dict:
    """
    1. section_writer 출력 (초안) + 원본 파일 읽기
    2. fact-checker 에이전트 호출
    3. 08_review/fact_check_report.json 생성
    """
```

#### `scripts/run_provenance_builder.py` — P7
```python
def run_provenance_builder(workspace: str) -> dict:
    """
    1. section_writer + internal_reviewer + fact_checker 출력 읽기
    2. provenance-builder 에이전트 호출
    3. 10_evidence_pack/evidence_chain.json 생성
    """
```

#### `scripts/run_handoff.py` — P6
```python
def run_handoff(workspace: str) -> dict:
    """
    1. 모든 검수 완료 초안 읽기
    2. draft_package.json 생성
    3. 09_handoff/에 최종 초안 복사
    """
```

---

### 3.4 `scripts/run_pipeline.py` [Session #20-D]

**역할:** 전체 P0→P7 파이프라인을 단일 명령으로 실행

```python
def run_pipeline(
    workspace: str,
    start_phase: str = "P0",
    end_phase: str = "P7",
    skip_approvals: bool = False,  # 테스트용
    parallel_sections: bool = True,  # 섹션별 병렬 실행
) -> PipelineResult:
    """
    1. state_manager 초기화
    2. 각 Phase 순차 실행:
       - Phase 진입 전 check_gate.py로 조건 확인
       - 해당 Phase 래퍼 실행
       - Phase 완료 후 project_state 갱신
       - 다음 Phase 진입 전 게이트 확인
    3. 완료 후 요약 보고
    """
```

**주요 로직:**
```python
PHASES = ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7"]

for phase in PHASES:
    if phase not in range_of(start_phase, end_phase):
        continue
    
    # 1. 게이트 확인
    gate_status = check_gate(workspace, phase)
    if gate_status.result == "blocked":
        if gate_status.can_override and skip_approvals:
            pass  # 테스트 모드: 계속 진행
        else:
            raise PipelineBlockedError(gate_status)
    
    if gate_status.result == "needs_human_approval":
        if not skip_approvals:
            wait_for_approval(gate_status.gate_id)
    
    # 2. Phase 실행
    result = PHASE_RUNNERS[phase](workspace)
    
    # 3. 상태 갱신
    state_manager.advance_phase(phase, NEXT_PHASE[phase])
    state_manager.sync()
```

**CLI 진입점:**
```bash
# 전체 파이프라인 실행
uv run python scripts/run_pipeline.py --workspace workspaces/PRJ-2026-CLNT-001

# P2부터 P5까지 (기존 P0-P1 스킵)
uv run python scripts/run_pipeline.py --workspace workspaces/PRJ-2026-CLNT-001 --start-phase P2 --end-phase P5

# 테스트 모드 (게이트 스킵)
uv run python scripts/run_pipeline.py --workspace workspaces/PRJ-2026-CLNT-001 --skip-approvals
```

**출력:**
```
=== Pipeline Run ===
RUN-20260403-A1 | workspace: PRJ-2026-CLNT-001

✅ P0 → P1 | completed (0.3s)
✅ P1 → P2 | completed (12.1s) | 3 files ingested, 8 segments extracted
⏳ P2 → P3 | waiting for human approval...
   [writing_blueprint.json awaiting consultant_lead approval]
   
--- PAUSED: Human approval required ---
Gate: P2_to_P3
Required approvers: project_manager, consultant_lead
```

**테스트:** `tests/test_pipeline.py` — 전체 플로우 모의 실행, 게이트 대기, 상태 갱신 검증

---

### 3.5 `scripts/wait_for_approval.py` [Session #20-E]

**역할:** 게이트 승인 대기 중 사용자에게 확인 요청

```python
def wait_for_approval(
    workspace: str,
    gate_name: str,
    required_approvers: list[str],
    timeout_seconds: int = None,
) -> ApprovalResult:
    """
    1. approval_gates.json에 대기 중 상태 기록
    2. 사용자에게 승인 요청 (CLI 입력 또는 파일 기반)
    3. 승인 시 approval_gates.json 갱신
    4. 거부 시 blocking_issue 추가
    """
```

**승인 방식:**
- **CLI:** 터미널에서 `y/n` 입력
- **파일 기반:** `approval_gates.json`을 편집기로 직접 수정
- **API (후순위):** REST API로 승인 요청 수신

---

## 4. 구현 순서 및 마일스톤

### Phase 1: 기초 모듈 (Session #20-A ~ B)
| 순서 | 작업 | 산출물 | 검증 |
|------|------|--------|------|
| 20-A-1 | `state_manager.py` 기본 구조 | `scripts/state_manager.py` | 단위 테스트 |
| 20-A-2 | Blocking Issue CRUD | `tests/test_state_manager.py` | 3/3 통과 |
| 20-B-1 | `dispatch_agent.py` 기본 구조 | `scripts/dispatch_agent.py` | 단위 테스트 |
| 20-B-2 | 프롬프트 로드 + 컨텍스트 조립 | `tests/test_dispatch_agent.py` | 5/5 통과 |

### Phase 2: Phase 실행 래퍼 (Session #20-C)
| 순서 | 작업 | 산출물 | 검증 |
|------|------|--------|------|
| 20-C-1 | `run_ingestion.py` | P1 파일 투입 스크립트 | 수동 테스트 |
| 20-C-2 | `run_toc_planner.py` + P2 게이트 대기 | P2 기획 스크립트 | 수동 테스트 |
| 20-C-3 | `run_framework_mapper.py` | P3 버킷 구축 스크립트 | 수동 테스트 |
| 20-C-4 | `run_section_writer.py` | P4 초안 작성 스크립트 | 수동 테스트 |
| 20-C-5 | `run_internal_reviewer.py` + `run_fact_checker.py` | P5 검수 스크립트 | 수동 테스트 |
| 20-C-6 | `run_handoff.py` + `run_provenance_builder.py` | P6/P7 스크립트 | 수동 테스트 |

### Phase 3: 파이프라인 조율 (Session #20-D)
| 순서 | 작업 | 산출물 | 검증 |
|------|------|--------|------|
| 20-D-1 | `run_pipeline.py`骨干 | 파이프라인 실행기 | E2E 테스트 |
| 20-D-2 | `wait_for_approval.py` | 승인 대기 핸들러 | 수동 테스트 |
| 20-D-3 | 전체 E2E 테스트 | PRJ-2026-TST-004 | TC-1~TC-8 재실행 |

---

## 5. Session #20 성공 기준

| 기준 | 검증 방법 |
|------|----------|
| `state_manager.py` 단위 테스트 3/3 통과 | `uv run python -m pytest tests/test_state_manager.py` |
| `dispatch_agent.py` 단위 테스트 5/5 통과 | `uv run python -m pytest tests/test_dispatch_agent.py` |
| P0→P1 자동 게이트 통과 | `check_gate.py` result = passed |
| P2→P3 게이트에서 승인 대기 | 수동 확인 |
| `run_pipeline.py` E2E 실행 성공 | 전체 P0→P7 완료 ( humano approval 대기 전) |
| Chinese/Japanese 문자 없음 | `grep` 검증 |

---

## 6. 발견된 버그 및 이슈

### 신규 발견
| ID | 설명 | 우선순위 | 대응 |
|----|------|---------|------|
| BUG-007 | `dispatch_agent.py` 부재 — 파이프라인 엔진 핵심缺 | **HIGH** | Session #20에서 구현 |
| BUG-008 | `state_manager.py` 부재 — Phase 상태 추적缺 | **HIGH** | Session #20에서 구현 |
| BUG-009 | Phase별 실행 스크립트 부재 — `run_*.py` 없음 | **HIGH** | Session #20에서 구현 |
| BUG-010 | `approval_gates.json` 대기 상태 관리 로직缺 | **MEDIUM** | `wait_for_approval.py`로 구현 |

---

## 7. Session #21 권장 과제

Session #20 완료 후 권장 작업:

1. **실제 파일 ingestion 테스트** — 실제 PDF/DOCX로 P1 파이프라인 검증
2. **병렬 섹션 작성** — `run_section_writer.py`를 멀티프로세스로 확장
3. **증거 자동 라우팅** — `run_framework_mapper.py`의 evidence→버킷 배정 자동화
4. **REST API** — `wait_for_approval.py`를 웹 API로 확장 (컨설턴트 승인 UI)

---

## 8. 산출물 목록

### Session #20 새로 생성 파일
```
scripts/
  state_manager.py              ← [NEW] Phase 상태 관리
  dispatch_agent.py             ← [NEW] 에이전트 호출 추상화
  run_pipeline.py               ← [NEW] 파이프라인 실행기
  wait_for_approval.py          ← [NEW] 게이트 승인 대기
  run_ingestion.py              ← [NEW] P1 파일 투입
  run_toc_planner.py            ← [NEW] P2 기획
  run_framework_mapper.py       ← [NEW] P3 버킷 구축
  run_section_writer.py         ← [NEW] P4 초안 작성
  run_internal_reviewer.py      ← [NEW] P5 내부 검수
  run_fact_checker.py           ← [NEW] P5 외부 검증
  run_handoff.py                ← [NEW] P6 핸드오프
  run_provenance_builder.py     ← [NEW] P7 증거 체인

tests/
  test_state_manager.py         ← [NEW]
  test_dispatch_agent.py        ← [NEW]
  test_pipeline.py              ← [NEW]
```

### Session #20 수정 파일
```
scripts/check_gate.py            ← state_manager 연동 강화
scripts/update_project_state.py  ← state_manager 호출로 통합
llm/router.py                   ← dispatch_agent에서 agent 필드 자동 전달
```
