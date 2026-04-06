# 구현 감사 체크리스트 (AUDIT_CHECKLIST) — ⚠️ superseded

> **⚠️ 이 파일은 더 이상 관리되지 않습니다.**
> 모든 수정 지시사항은 **`NEXT_SESSION_DIRECTIVES.md`** 로 통합되었습니다.
> 세션 #9 작업은 해당 파일을 참조하세요.

**원본 생성일:** Session #8  
**병합 출처:** `AUDIT_DIRECTIVES.md` (사용자 검토) + 본 체크리스트 (병렬 감사)  
**통합 파일:** `NEXT_SESSION_DIRECTIVES.md`

---

## 1. Orchestration JSON 파일 (5개)

| # | 우선순위 | 파일 | 이슈 | 작업 지시 | 상태 |
|---|---------|------|------|----------|------|
| 1.1 | 🔴 CRITICAL | `agent_runtime_policy.json` | provenance-builder: CLAUDE.md는 P7, runtime_policy는 P6 | lifecycle.start을 `"P7 단계에서"`로 수정. phase_rules.json P7 required_outputs와 일치 확인 | 🔴 |
| 1.2 | 🟡 HIGH | `gate_rules.json` | P5_to_P6 `required_approvers`가 agent 이름 (`fact_checker`, `internal_reviewer`) — human approval에 부적합 | `required_approvers`를 human stakeholder 이름으로 변경 (예: `["project_manager", "consultant_lead"]`) 또는 `approval_type`이 automated이면 명시 | 🟡 |
| 1.3 | 🟡 HIGH | `agent_contracts.json` | fact-checker, provenance-builder가 `style_guide.json`과 `terminology_dictionary.json` 미참조 — CLAUDE.md "모든 서브에이전트" 규칙 위반 | 두 에이전트의 `input_contracts.required`에 guidance 파일 2개 추가 | 🟡 |
| 1.4 | 🟡 MEDIUM | `phase_rules.json` | `gate_required: true`인 phases에 `gate_id` 필드 없음 — naming convention 의존 | P2, P5 phases에 `"gate_id": "P2_to_P3"`, `"gate_id": "P5_to_P6"` 추가 | 🟡 |
| 1.5 | 🟡 MEDIUM | `gate_rules.json` | auto_gate description "P6→P7 자동 처리" vs phase_rules P6→P7 명시적 정의 없음 | phase_rules P6→P7 transition에 `gate_required: false` 명시, gate_rules auto_gate.applies_to에 `"P6_to_P7"` 추가 | 🟡 |
| 1.6 | 🟡 LOW | `gate_rules.json`, `phase_rules.json` | `$id`가 local schema 파일을 참조하지 않음 | `schemas/gate_rules.schema.json`, `schemas/phase_rules.schema.json` 생성 또는 $schema/$id 제거 | 🟡 |
| 1.7 | 🟡 LOW | `agent_contracts.json` | internal-reviewer가 `style_guide.json` 없이 `terminology_dictionary.json`만 참조 | internal-reviewer `input_contracts.required`에 `guidance/style_guide.json` 추가 | 🟡 |

---

## 2. Python 스크립트 (8개)

| # | 우선순위 | 파일 | 라인 | 이슈 | 작업 지시 | 상태 |
|---|---------|------|------|------|----------|------|
| 2.1 | 🟡 HIGH | `scripts/check_gate.py` | `_check_required_outputs()` | entry_conditions 검증 안 함 (phase_rules.json entry_conditions 있음) | `_check_entry_conditions()` 함수 추가 — phase_rules의 entry_conditions별 검증 로직 구현 | 🟡 |
| 2.2 | 🟡 HIGH | `scripts/update_project_state.py` | `_all_bucket_files_exist()`, `_all_draft_meta_files_exist()` | `len() > 0` 체크 — **any** 파일 존재 여부만 확인, **all** required 아님 | `SEG-NNNNN` 매니페스트 읽어서 전체 required 파일 목록 생성 후 전부 존재 확인으로 변경 | 🟡 |
| 2.3 | 🟡 HIGH | `scripts/log_event.py` | `get_active_run()` in `log_gate_blocked()`, `log_incident()` | `run_id`를 return하지만 event record에 포함 안 함 | 두 함수에서 `run_id`를 event dict에 추가 (`"run_id": run_id` 삽입) | 🟡 |
| 2.4 | 🟡 MEDIUM | `scripts/init_workspace.py` | `base_path` 기본값 | `Path("workspaces")` — cwd 기준 상대경로 | `Path(__file__).parent.parent / "workspaces"`로 변경하거나 절대경로 요구 | 🟡 |
| 2.5 | 🟡 MEDIUM | `scripts/log_event.py` | `LOG_DIR = "context_bus"` | workspace 없이 실행 시 `./context_bus/`에 기록 | workspace 인자 없이 호출 시警告 또는 오류 발생시키는 가드 추가 | 🟡 |
| 2.6 | 🟡 MEDIUM | `scripts/rebuild_summaries.py` | `generate_next_actions()` | `phase_rules` 파라미터 받지만 `current_phase`, `next_phase`만 사용 | exit_conditions 기반 스마트 next action 생성 로직 보강 (예: missing_outputs로부터 다음 단계 추론) | 🟡 |
| 2.7 | 🟡 MEDIUM | `scripts/normalize.py` | `extract_metadata()` | 테이블検出 heuristic `"\\n| ---"` 너무 단순 | `\|---|`, `\| --- |`, `| :-- |` 등 변형 모두 지원 또는 markdownlib 사용 고려 | 🟡 |
| 2.8 | 🟡 MEDIUM | `llm/call_log.py` | `CONTEXT_BUS_DIR = Path("context_bus")` | workspace 상대 아닌 cwd 기준 | `get_context_bus_dir(workspace: Path)` 함수로 분리 — caller가 전달 | 🟡 |
| 2.9 | 🟡 MEDIUM | `llm/router.py` | `CALL_LOG_PATH = "llm/call_log.jsonl"` | workspace 상대 아닌 cwd 기준 | `workspace / "llm" / "call_log.jsonl"`로 변경 | 🟡 |
| 2.10 | 🟡 LOW | `scripts/check_gate.py` | `_load_json()` | `FileNotFoundError`를 `{}`로 swallow — 디버깅 어려움 | `except (FileNotFoundError, JSONDecodeError) as e: logger.warning(f"Failed to load {path}: {e}")` 후 `return {}` 유지 | 🟡 |
| 2.11 | 🟡 LOW | `scripts/rebuild_summaries.py` | `merge_blocking_issues()` | `description[:80]`으로 deduplication — 80자 이후 다름→merged | 전체 description 또는 hash 기반 dedup으로 변경 | 🟡 |
| 2.12 | 🟡 LOW | `llm/router.py` | `generate_run_id()` | `/tmp/.sustainreport_run_seq_{date}` — concurrent process 충돌 가능 | workspace-specific tempdir 사용 또는 `tempfile.mkstemp()`로 atomic 파일 creation | 🟡 |

---

## 3. Agent 프롬프트 일관성 (7 agents × 2 locations)

| # | 우선순위 | Agent | 위치 | 이슈 | 작업 지시 | 상태 |
|---|---------|-------|------|------|----------|------|
| 3.1 | 🔴 CRITICAL | `internal-reviewer` | `agents/internal-reviewer.md`, `.claude/agents/internal-reviewer.md` | guidance 파일 3개 (`writing_blueprint.json`, `style_guide.json`, `terminology_dictionary.json`) 모두 input contracts에 미기재 — work_rules에는 terminology consistency check 언급 | input contracts 표에 3개 파일 모두 **필수**로 추가 | 🟡 |
| 3.2 | 🔴 CRITICAL | `data-analyst` | `.claude/agents/data-analyst.md` | `agents/data-analyst.md`의 hallucination 방지 조항 ("출처 없는 메타데이터 추정 금지") 누락 | `.claude/agents/data-analyst.md`의 `## 금지 사항` 또는 `## 작업 규칙`에 hallucination 방지 문구 추가 | 🟡 |
| 3.3 | 🟡 HIGH | `fact-checker` | `agents/fact-checker.md`, `.claude/agents/fact-checker.md` | guidance 파일 (`style_guide.json`, `terminology_dictionary.json`) "필요시"로 기재 — agent_contracts.json은 required | "필요시" → **"필수"**로 변경 | 🟡 |
| 3.4 | 🟡 HIGH | `provenance-builder` | `agents/provenance-builder.md`, `.claude/agents/provenance-builder.md` | guidance 파일 3개 모두 미참조 — CLAUDE.md "모든 서브에이전트" 규칙 위반 | input contracts 표에 `guidance/style_guide.json`, `guidance/terminology_dictionary.json` 추가 | 🟡 |
| 3.5 | 🟡 HIGH | `toc-planner` | `agents/toc-planner.md`, `.claude/agents/toc-planner.md` | `writing_blueprint.json`을 output으로는 명시하지만 **input으로 참조 안 함** (재진입 시 기존 blueprint 읽어야 함) | input contracts 표에 `guidance/writing_blueprint.json` 추가 (재진입 시 필요) | 🟡 |
| 3.6 | 🟡 MEDIUM | `data-analyst` | `agents/data-analyst.md`, `.claude/agents/data-analyst.md` | `style_guide.json`, `terminology_dictionary.json` "선택" 기재 | CLAUDE.md "모든 에이전트 참조" 규칙과 일치하도록 "참고" 또는 "필수"로 재분류 | 🟡 |
| 3.7 | 🟡 MEDIUM | 모든 `.claude/agents/*.md` | `.claude/agents/*.md` (7개) | `agents/` 대비 prohibition 언어 누락 차이 존재 (`data-analyst`에서 확인) | 7개 agents 쌍 비교하여 누락된 prohibition/작업규칙 각도 보충 | 🟡 |

---

## 4. JSON Schema 파일 (8개)

| # | 우선순위 | 파일 | 이슈 | 작업 지시 | 상태 |
|---|---------|------|------|----------|------|
| 4.1 | 🟡 MEDIUM | `schemas/draft_queries.schema.json` | `dq_id` pattern `^DQ-\\d{3}$` (3자리固定) — CLAUDE.md 표기 `DQ-NNN`과 차이 | 패턴을 `^DQ-\\d{1,3}$`로 변경 (001~999 의미 명확화) 또는 README에 leading zero 정책 명시 | 🟡 |
| 4.2 | 🟡 MEDIUM | `schemas/framework_index.schema.json` | `framework_code` enum에 `KSSB_S2` (underscore) vs 다른 schema `KSSB` 불일치 | `KSSB` 시리즈统일 (underscore 제거). KSSB 표준 명칭 확인 후 일관 코드로 교체 | 🟡 |
| 4.3 | 🟡 LOW | `schemas/file_registry.schema.json` | root level에 `title` 필드 없음 (다른 schema와 불일치) | `title: { type: "string" }` 추가 | 🟡 |
| 4.4 | 🟡 LOW | 모든 schema | `phase` enum이 어디에도 P0-P7.constraining 없음 | `phase` enum 정의하는 shared `$def` 생성 또는 각 schema에 명시적 phase enum 추가 | 🟡 |

---

## 5. Template / Framework DB (5개)

| # | 우선순위 | 파일 | 이슈 | 작업 지시 | 상태 |
|---|---------|------|------|----------|------|
| 5.1 | 🔴 CRITICAL | `templates/framework_db/tcfd_db.json` | G4 `recommended_metrics`에 incomplete string: `" istrumen` (切 truncation) | G4 관련 `recommended_metrics` 전체 재입력 또는 원본 출처確認 후 수정 | 🟡 |
| 5.2 | 🔴 CRITICAL | `templates/framework_db/kssb_db.json` | `disclosure_requirements`에 Chinese characters 혼입 (`温室가스`, `的员工数`, `强迫노동`) | Korean term으로 전량 교체 — `탄소가스`, `총직원수`, `강제노동` 등 | 🟡 |
| 5.3 | 🟡 HIGH | `templates/framework_db/esrs_db.json` | `data_point` 배열에 leading/trailing whitespace 불일치 (예: `" 기후변화 관련 전략"` 선행 공백) | 모든 `data_point` 문자열 `.strip()` 후 재저장 | 🟡 |
| 5.4 | 🟡 MEDIUM | 모든 framework_db | root 구조 불일치: ESRS/GRI는 `standards`, KSSB는 `framework`, SASB는 `industries`, TCFD는 `disclosures` | `disclosures` 또는 `requirements`로統一 `--preferred_key` 플래그 추가 고려 | 🟡 |
| 5.5 | 🟡 MEDIUM | 모든 framework_db | version 필드 위치 불일치: ESRS/GRI/SASB는 `version`, KSSB/TCFD는 `_meta.schema_version` | `_meta.schema_version` 으로統一 | 🟡 |

---

## 6. Guidance 파일 (2개)

| # | 우선순위 | 파일 | 이슈 | 작업 지시 | 상태 |
|---|---------|------|------|----------|------|
| 6.1 | 🔴 CRITICAL | `guidance/style_guide.json` | `numeric_expression` 필드 값이 corrupted mixed-script text: `"阿拉伯数字優先 (수치는 숫자, 단위: tCO2e, GWh 등)"` | pure Korean으로 교체: `"수치 표현:阿拉伯数字優先, 단위: tCO2e, GWh 등"` 또는 `"수치: 숫자 사용, 단위: tCO2e, GWh 등"` | 🟡 |
| 6.2 | 🟡 MEDIUM | `guidance/terminology_dictionary.json` | `Scope 3`의 `term_ko`에 오타: `"기타 간실 온실가스 배출량"` → `"기타 간접 온실가스 배출량"` (간실→간접) | `Scope 3.term_ko` 값 수정 | 🟡 |
| 6.3 | 🟡 LOW | `guidance/terminology_dictionary.json` | `RE100` 항목에 `usage` 필드 누락 (`term_ko`, `term_en`만 존재) | `usage` 필드 추가: `"글로벌 재생에너지 100% 전환 목표"` | 🟡 |

---

## 7. 공통 아키텍처 이슈 (cross-cutting)

| # | 우선순위 | 범위 | 이슈 | 작업 지시 | 상태 |
|---|---------|------|------|----------|------|
| 7.1 | 🔴 CRITICAL | 전역 | **Workspace 상대경로 문제** — `context_bus/`, `llm/`, `workspaces/` 가 cwd 기준 상대경로로 하드코딩된 위치 다수 | 모든 스크립트에서 workspace 경로를 명시적으로 받거나 `Path(__file__).parent.parent` 기준 절대경로 사용하도록 수정 | 🟡 |
| 7.2 | 🟡 HIGH | 전역 | **P2 artifact 生成 체인 미문서화** — `framework_index.json`은 toc-planner가 아닌 framework-mapper가 생성 → P2 완료 위해 2개 agent 연쇄 필요 | `orchestration/phase_rules.json` P2 required_outputs에 주석 추가: "framework_index.json은 framework-mapper agent 출력" | 🟡 |
| 7.3 | 🟡 HIGH | phase_rules | **entry_conditions 검증 부재** — phase_rules.json에 정의된 entry_conditions를 check_gate.py가 검증 안 함 | `_check_entry_conditions()` 구현 (항목 2.1 참조) | 🟡 |
| 7.4 | 🟡 MEDIUM | 전역 | **auto_gate has no machine-readable `applies_to`** — 어떤 transition에 적용되는지 description 문자열만 | `gate_rules.json`의 `auto_gate`에 `"applies_to": ["P0_to_P1", "P1_to_P2", ...]` 명시적 리스트 추가 | 🟡 |

---

## 진행 기준

| 우선순위 | 의미 | 대응 기한 |
|---------|------|---------|
| 🔴 CRITICAL | 런타임 오류 또는 데이터 무결성 위협 — **반드시 다음 세션에 수정** | 다음 세션 |
| 🟡 HIGH | 기능 오류 또는 설계 불일치 — **세션 내 수정 대상** | 이번审计 완료 전 |
| 🟡 MEDIUM | 품질/일관성 문제 — **예정된 개선** | 향후 sprints |
| 🟡 LOW | 사소한 문제 — **음성 개선** | 여유 시 |

---

## 체크리스트 진행률

| 카테고리 | 총 이슈 | ✅ 완료 | 🔴 미시작 | 🟡 진행중 |
|---------|--------|--------|----------|----------|
| 1. Orchestration JSON | 7 | 0 | 7 | 0 |
| 2. Python Scripts | 12 | 0 | 12 | 0 |
| 3. Agent Prompts | 7 | 0 | 7 | 0 |
| 4. JSON Schemas | 4 | 0 | 4 | 0 |
| 5. Framework DBs | 5 | 0 | 5 | 0 |
| 6. Guidance Files | 3 | 0 | 3 | 0 |
| 7. Cross-Cutting | 4 | 0 | 4 | 0 |
| **합계** | **42** | **0** | **42** | **0** |

---

## 다음 세션 작업 우선순위

1. **🔴 1.1** provenance-builder phase 교정 (P6→P7) — CLAUDE.md와 phase_rules.json 일치
2. **🔴 3.1** internal-reviewer guidance 파일 추가 — 초안검증 기능 필수
3. **🔴 3.2** data-analyst hallucination 방지 조항 보충
4. **🔴 5.1** TCFD G4 incomplete string 수정 — 데이터 무결성
5. **🔴 5.2** KSSB Chinese characters一괄 교체 — 데이터 무결성
6. **🔴 6.1** style_guide.json corrupted field 수정
7. **🔴 7.1** workspace 상대경로 문제— 스크립트 실행 위치 의존성 제거