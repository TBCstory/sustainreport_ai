# Implementation Execution Directives

작성일: 2026-04-04

이 문서는 2026-04-04 런타임 검증 결과를 반영한 **재구현용 실행 지시문**이다.

중요:

- 2026-04-03 기준 `WP-1~7 DONE` 표기는 "문서상 완료"에 가깝고, 실제 happy path 검증에서는 여러 핵심 흐름이 아직 깨져 있었다.
- 따라서 다음 코딩 에이전트는 **기존 DONE 주장보다 이 문서를 우선**한다.
- 이번 라운드의 목표는 새 기능 확장이 아니라, **이미 약속한 PoC를 실제로 작동하게 복구하는 것**이다.
- 2026-04-05 기준 runtime remediation은 대부분 닫혔지만, **원 설계 acceptance gap**은 별도 cycle로 남아 있다.
- original design acceptance gap을 닫는 세션은 `ORIGINAL_DESIGN_GAP_CLOSURE_PLAN.md`를 함께 읽고, 그 문서의 packet 순서를 따른다.

---

## 0. 왜 이 문서를 다시 쓰는가

실제 검증에서 아래 문제가 재현되었다.

1. `llm/cli.py approve`가 canonical approval shape를 갱신하지 않아, `check-gate` 결과와 polling 대기가 서로 다른 상태를 보았다.
2. `scripts/run_toc_planner.py`가 아직도 `승인 대기 -> 생성` 순서로 동작해, WP-2 완료 기준과 불일치했다.
3. live P2 실행 시 toc-planner 출력이 JSON으로 안정적으로 파싱되지 않았다.
4. `scripts/run_section_writer.py`가 sample `writing_blueprint.json`의 실제 shape(list)를 처리하지 못해 런타임 예외가 났다.
5. `scripts/run_section_writer.py`는 `save_draft()` 호출 인자 순서도 잘못되어 추가 런타임 실패가 있었다.
6. `scripts/run_ingestion.py`는 CLI 환경에서 `markitdown`을 찾지 못해 nested raw ingest smoke test가 실패했다.
7. `update-state`, `status`, `run-pipeline --dry-run`이 같은 workspace를 서로 다르게 설명했다.
8. `python -m compileall scripts llm`은 `scripts/` 아래의 pseudo file 때문에 실패했다.

---

## 1. 이 문서의 사용법

1. 이 문서를 읽고, **아직 완료되지 않은 가장 앞 remediation packet 하나만** 선택한다.
2. 선택한 packet의 `필수 읽기 파일`만 추가로 읽는다.
3. packet 범위를 넘는 수정이 필요해 보여도 즉시 확장하지 않는다.
4. 현재 packet을 acceptance criteria까지 최대한 닫고, 넘어가는 작업은 handoff에 남긴다.
5. 세션 종료 시 반드시 `IMPLEMENTATION_PROGRESS.md`와 `SESSION_LOG.md`를 갱신한다.

---

## 2. 절대 바꾸지 말아야 할 목표

다음 목표는 이번 remediation에서도 고정이다.

1. 이 시스템은 **최종 납품본 생성기**가 아니라 **근거 기반 초안 생성기**다.
2. 증거가 없으면 수치/사실을 쓰지 않고 placeholder 또는 query로 남겨야 한다.
3. 승인 없는 자동 통과를 늘리면 안 된다.
4. 컨설턴트는 JSON을 직접 편집하는 운영자가 아니라, 초안/질의/다음 행동을 소비하는 사용자다.
5. 지금 단계의 1차 목표는 **파일 기반 CLI PoC 안정화**이지 웹앱 구축이 아니다.

---

## 3. 명시적 비목표

아래 작업은 이번 라운드에서 금지한다.

- 새 프레임워크/새 모델 정책 추가
- 대규모 패키지 구조 개편
- DB, 서버, 웹 UI, 인증 시스템 도입
- 보고서 최종 편집기 구축
- phase runner 전면 리라이트
- 사용자가 요청하지 않은 신규 의존성 추가
- "정리 차원"의 광범위한 문서/코드 재포맷

---

## 4. 세션 운영 규칙

### 4.1 세션당 작업량 제한

- 한 세션에서 **한 remediation packet만 수행**한다.
- 한 세션에서 **핵심 파일 6개 이상** 수정하지 않는다.
- 테스트 파일은 별도지만 가능하면 packet당 1~3개만 추가/수정한다.

### 4.2 공통 필수 읽기

매 세션 시작 시 아래 파일만 먼저 읽는다.

- `AGENTS.md`
- `CLAUDE.md`
- `GAP_REMEDIATION_UPDATE_PLAN.md`
- `IMPLEMENTATION_EXECUTION_DIRECTIVES.md`
- `IMPLEMENTATION_PROGRESS.md`

그 다음에는 선택한 packet의 `필수 읽기 파일`만 읽는다.

`purrfect-riding-blossom.md` 전체는 매 세션 공통 필수 읽기 대상이 아니다.
원 설계 의도가 직접 필요할 때만 필요한 섹션만 부분 참조한다.

### 4.3 세션 시작 보고 형식

공통 필수 읽기와 packet 필수 읽기를 마친 뒤, 아래 형식으로 먼저 보고한다.

1. 이번 세션에서 수행할 packet 이름
2. 읽을 추가 파일 목록
3. 수정 예정 파일 목록
4. 이번 packet에서 하지 않을 것 3개 이하
5. 완료 기준

이 단계에서는 아직 코드를 수정하지 않는다.

### 4.4 중단 기준

아래 중 하나가 발생하면 scope를 넓히지 말고 중단/기록한다.

- packet 외 파일까지 3개 이상 연쇄 수정이 필요함
- schema 변경이 2개 이상 동반됨
- 새로운 의존성이 필요함
- 승인 정책 해석이 애매함
- 기존 산출물 shape를 깨는 변경이 필요함
- live LLM/network failure가 core bug와 무관하게 작업을 막음

### 4.5 live 검증에 대한 규칙

- live command가 실패하면 먼저 **deterministic regression test**로 현재 bug를 고정한다.
- live 검증까지 닫히지 못해도 packet 범위를 넘는 리팩터링으로 도망가지 않는다.
- live failure가 prompt/parser 문제인지 infra 문제인지 handoff에 분리해 적는다.

---

## 5. 검증용 임시 워크스페이스 규칙

canonical sample workspace는 직접 망가뜨리지 않는다.

권장 검증용 경로:

- P2/P5/state 검증: `/tmp/sustainreport_review_state`
- P2 planning 검증: `/tmp/sustainreport_review_toc`
- P1 ingestion 검증: `/private/tmp/PRJ-2026-TMP-ING01`

필요 시 `workspaces/PRJ-2026-TST-003`을 복사해서 사용한다.

---

## 6. 목표 사용 흐름

이번 remediation 완료 후 최소 아래 흐름이 다시 살아야 한다.

### Flow A. 운영자 happy path

1. workspace 생성
2. raw 자료 투입
3. ingestion 실행
4. planning 실행
5. approval 처리
6. section draft 실행
7. review / handoff / evidence pack 진행

### Flow B. 섹션 담당 컨설턴트 happy path

1. 현재 프로젝트 상태 확인
2. 자신이 맡은 섹션만 draft 실행
3. open query / missing evidence 확인
4. 보강 자료 요청
5. 동일 섹션 재실행

### Flow C. 리드/리뷰어 happy path

1. 현재 gate 상태 확인
2. blocking issue / next action 확인
3. 승인 기록
4. handoff 가능 여부 판단

---

## 7. Remediation Packet 목록

작업은 아래 순서를 따른다. 앞 packet이 끝나기 전에는 다음 packet으로 가지 않는다.

### WP-R1. Approval Canonicalization

상태: TODO

목표:

- 승인 파일 shape를 canonical form 하나로 고정하고, CLI 승인과 gate polling이 같은 상태를 보게 만든다.

필수 읽기 파일:

- `llm/cli.py`
- `scripts/state_manager.py`
- `scripts/check_gate.py`
- `scripts/wait_for_approval.py`
- `scripts/run_pipeline.py`
- `tests/test_state_manager.py`
- `tests/test_dispatch_agent.py`
- `workspaces/PRJ-2026-TST-003/approval_gates.json`

수정 가능 파일:

- `llm/cli.py`
- `scripts/state_manager.py`
- `scripts/check_gate.py`
- `scripts/wait_for_approval.py`
- `scripts/run_pipeline.py`
- `tests/test_state_manager.py`
- `tests/test_dispatch_agent.py`

수정 금지:

- `scripts/run_toc_planner.py`
- `scripts/run_section_writer.py`
- `README.md`

구체 작업:

1. `approve` 명령은 직접 legacy shape를 쓰지 말고 canonical helper를 통해 기록한다.
2. canonical approval shape는 아래 필드를 기준으로 통일한다.
   - `status`: `waiting|approved|rejected`
   - `decision`: `approved|rejected|null`
   - `required_approvers`
   - `current_approvers`
   - `requested_at`
   - `decided_at`
   - `decided_by`
3. backward compatibility는 **읽기에서만** 유지한다.
4. `check_gate.py`, `wait_for_approval.py`, `run_pipeline.py`는 canonical 우선으로 판정한다.
5. 최소 1개의 regression test를 추가해 `waiting -> approved -> passed` 흐름을 검증한다.

완료 기준:

- temp workspace에서 1인 승인 후 `waiting`, 필수 승인자 완료 후 `approved`가 된다.
- `check-gate P2_to_P3`와 file polling 결과가 동일하다.
- `approved_by`만 있는 상태에 의존하지 않는다.

검증 명령:

```bash
.venv/bin/pytest tests/test_dispatch_agent.py tests/test_state_manager.py -q
```

세션 종료 시 handoff에 반드시 적을 것:

- canonical approval shape exact example
- legacy read compatibility 유지 범위
- CLI approve가 어떤 helper를 타도록 바뀌었는지

---

### WP-R2. P2 Planning Flow Recovery

상태: TODO

목표:

- P2를 `생성 -> 파싱 -> 저장 -> 승인 대기` 순서로 복구하고, live planner 출력 파싱을 안정화한다.

필수 읽기 파일:

- `scripts/run_toc_planner.py`
- `agents/toc-planner.md`
- `llm/router.py`
- `schemas/writing_blueprint.schema.json`
- `schemas/structure_index.schema.json`
- `workspaces/PRJ-2026-TST-003/05_planning/writing_blueprint.json`
- `workspaces/PRJ-2026-TST-003/05_planning/structure_index.json`
- `workspaces/PRJ-2026-TST-003/05_planning/section_manifest.json`

수정 가능 파일:

- `scripts/run_toc_planner.py`
- `agents/toc-planner.md`
- 필요 시 `tests/` 신규 테스트 1개

수정 금지:

- `scripts/run_section_writer.py`
- `scripts/dispatch_agent.py`
- `llm/router.py`의 광범위한 정책 변경

구체 작업:

1. `run_toc_planner.py` 실행 순서를 `LLM 호출 -> planning bundle 파싱 -> 3개 파일 저장 -> 승인 대기`로 바꾼다.
2. `parse_planning_bundle()`를 강화한다.
   - fenced code block 허용
   - 전후 설명문이 있어도 JSON object만 추출 시도
   - 빈 응답/비JSON 응답에 대해 명확한 에러 메시지 제공
3. saved outputs는 approval 전에도 남아 있어야 한다.
4. `agents/toc-planner.md`는 단일 JSON object shape를 더 강하게 요구한다.
5. 가능하면 packet-local regression test를 추가해 "승인 대기 전에 파일이 생성되어 있음"을 고정한다.

완료 기준:

- temp workspace에서 P2가 세 파일을 생성한다.
- 승인 전에도 `05_planning/*.json`이 남는다.
- live planner 출력이 JSON parse failure 없이 통과하거나, parse failure 원인이 deterministic test와 handoff로 분리된다.

검증 명령:

```bash
.venv/bin/python scripts/run_toc_planner.py --workspace /tmp/sustainreport_review_toc --skip-approval
.venv/bin/pytest tests -q
```

세션 종료 시 handoff에 반드시 적을 것:

- planning bundle exact JSON shape
- parser가 허용하는 출력 패턴
- live run 성공 여부와 실패 시 raw failure 유형

---

### WP-R3. Section Writer Runtime Recovery

상태: TODO

목표:

- P4가 sample blueprint shape와 실제 함수 시그니처를 처리하도록 복구한다.

필수 읽기 파일:

- `scripts/run_section_writer.py`
- `agents/section-writer.md`
- `workspaces/PRJ-2026-TST-003/05_planning/writing_blueprint.json`
- `workspaces/PRJ-2026-TST-003/05_planning/structure_index.json`
- `workspaces/PRJ-2026-TST-003/06_buckets/SEC-3.1.json`
- `workspaces/PRJ-2026-TST-003/draft_queries.json`

수정 가능 파일:

- `scripts/run_section_writer.py`
- 필요 시 `agents/section-writer.md`
- 필요 시 `tests/` 신규 테스트 1개

수정 금지:

- `scripts/run_fact_checker.py`
- `scripts/run_handoff.py`
- `schemas/draft_queries.schema.json`의 무관한 확장

구체 작업:

1. `writing_blueprint["sections"]`가 list 또는 dict여도 처리되도록 normalize helper를 만든다.
2. `save_draft()` 호출 인자 순서를 수정한다.
3. `write_single_section()` regression test를 추가한다.
   - list-shaped blueprint
   - fake dispatcher
   - placeholder -> query 등록
4. 기존 query dedupe rule과 metadata field names는 유지한다.
5. 이 packet에서는 overwrite UX 확장이나 broad rerun workflow를 만들지 않는다.

완료 기준:

- sample-style blueprint에서 `write_single_section()`이 예외 없이 성공한다.
- `draft_confidence`, `confidence`, `placeholder_count`, `source_tag_count`가 메타에 기록된다.
- placeholder가 query로 이어진다.

검증 명령:

```bash
.venv/bin/pytest tests -q
```

세션 종료 시 handoff에 반드시 적을 것:

- blueprint section normalization rule
- save_draft bug 원인과 수정 방식
- 추가한 regression test 범위

---

### WP-R4. Ingestion CLI Path Recovery

상태: TODO

목표:

- CLI 환경에서 `markitdown`을 안정적으로 찾아 nested raw ingestion이 실제로 성공하게 만든다.

필수 읽기 파일:

- `scripts/run_ingestion.py`
- `scripts/init_workspace.py`
- `workspaces/PRJ-2026-TST-003/01_raw/test_report.txt`

수정 가능 파일:

- `scripts/run_ingestion.py`
- 필요 시 `scripts/init_workspace.py`
- 필요 시 `tests/` 신규 테스트 1개

수정 금지:

- `scripts/normalize.py` 대규모 재작성
- `llm/cli.py`
- `README.md`

구체 작업:

1. `run_ingestion.py`의 markitdown 호출은 bare command에만 의존하지 않게 한다.
   - 현재 interpreter 기준 sibling executable 우선
   - `.venv/bin/markitdown` 또는 equivalent fallback 허용
   - 마지막 fallback으로 PATH 사용 가능
2. 기존 `rglob` 기반 재귀 수집과 workspace-level segment counter는 유지한다.
3. `source_path`는 workspace 상대경로를 유지한다.
4. 가능하면 nested raw ingest regression test를 추가한다.

완료 기준:

- temp workspace에서 nested raw 폴더 2개 txt 파일 ingestion 성공
- segment ID가 `SEG-00001`, `SEG-00002` 식으로 충돌 없이 증가
- CLI 기준으로 `markitdown command not found`가 사라진다

검증 명령:

```bash
.venv/bin/sustainreport init-workspace PRJ-2026-TMP-ING01 --base-path /private/tmp
mkdir -p /private/tmp/PRJ-2026-TMP-ING01/01_raw/nested/deeper
cp workspaces/PRJ-2026-TST-003/01_raw/test_report.txt /private/tmp/PRJ-2026-TMP-ING01/01_raw/top.txt
cp workspaces/PRJ-2026-TST-003/01_raw/test_report.txt /private/tmp/PRJ-2026-TMP-ING01/01_raw/nested/deeper/deep.txt
.venv/bin/sustainreport run-ingestion /private/tmp/PRJ-2026-TMP-ING01
.venv/bin/pytest tests -q
```

세션 종료 시 handoff에 반드시 적을 것:

- markitdown resolution order
- nested ingest smoke test 결과
- segment counter 검증 결과

---

### WP-R5. State / Gate Consistency Recovery

상태: TODO

목표:

- `update-state`, `status`, `check-gate`, `run-pipeline --dry-run`이 같은 workspace를 일관되게 설명하도록 맞춘다.

필수 읽기 파일:

- `scripts/update_project_state.py`
- `scripts/rebuild_summaries.py`
- `scripts/check_gate.py`
- `llm/cli.py`
- `workspaces/PRJ-2026-TST-003/project_state.json`
- `workspaces/PRJ-2026-TST-003/blocking_issues.json`
- `workspaces/PRJ-2026-TST-003/next_actions.json`
- `workspaces/PRJ-2026-TST-003/05_planning/section_manifest.json`

수정 가능 파일:

- `scripts/update_project_state.py`
- `scripts/rebuild_summaries.py`
- `scripts/check_gate.py`
- `llm/cli.py`
- 필요 시 `tests/` 신규 테스트 1개

수정 금지:

- `scripts/run_handoff.py`
- framework DB
- schema mass migration

구체 작업:

1. phase summary와 gate evaluation이 서로 모순되지 않게 한다.
2. sample workspace에서 `P7 artifacts 존재`와 `current_phase P3` 같은 모순이 왜 생기는지 정리하고 수정한다.
3. `status` 출력은 현재 phase, unresolved issue count, open query count, next action top 3을 계속 보여주되 실제 phase story를 따르게 만든다.
4. manual section exclusion과 section_manifest 우선 규칙은 유지한다.
5. sample workspace 자체가 내부적으로 모순되면 fixture-safe regression test를 추가하고, packet 범위 밖 샘플 수정은 신중히 제한한다.

완료 기준:

- 같은 temp workspace에 대해 `update-state`, `status`, `run-pipeline --dry-run`, `check-gate`가 같은 현실을 설명한다.
- P2 gate passed 여부와 phase summary가 정면충돌하지 않는다.

검증 명령:

```bash
.venv/bin/python scripts/rebuild_summaries.py --workspace /tmp/sustainreport_review_state
.venv/bin/sustainreport update-state --workspace /tmp/sustainreport_review_state
.venv/bin/sustainreport status --workspace /tmp/sustainreport_review_state
.venv/bin/sustainreport run-pipeline --workspace /tmp/sustainreport_review_state --dry-run
```

세션 종료 시 handoff에 반드시 적을 것:

- phase calculation rule 변화
- sample workspace inconsistency 여부
- status/dry-run/check-gate alignment 결과

---

### WP-R6. Verification / Closeout and Architecture Gap Baseline

상태: TODO

목표:

- regression test 사각지대를 줄이고, 초기 계획서에 명시했지만 아직 없는 baseline artifact를 채운다.

필수 읽기 파일:

- `scripts/fix_files.py`
- `scripts/fix_corrupted_files.py`
- `purrfect-riding-blossom.md`
- `orchestration/phase_rules.json`
- `orchestration/gate_rules.json`

수정 가능 파일:

- `scripts/fix_files.py`
- `scripts/fix_corrupted_files.py`
- `orchestration/session_registry.json` 신규
- `orchestration/context_sync_rules.json` 신규
- `orchestration/next_action_policy.md` 신규
- `orchestration/fallback_routes.json` 신규
- 필요 시 `tests/` 신규 테스트 1개

수정 금지:

- core phase runner 대수술
- model routing 대확장
- web/TUI 도입

구체 작업:

1. `python -m compileall scripts llm`이 깨지는 pseudo file 문제를 정리한다.
2. 초기 계획서에 명시된 orchestration baseline artifact 4개를 생성한다.
3. 새 파일은 lightweight baseline이면 충분하다. 복잡한 런타임 연결까지 이번 packet에서 끝내려고 하지 않는다.
4. 남는 gap은 `IMPLEMENTATION_PROGRESS.md`와 `SESSION_LOG.md`에 명확히 남긴다.

완료 기준:

- `python -m compileall scripts llm` 통과
- 위 4개 orchestration artifact 존재
- 남은 gap이 "무엇이 아직 미구현인지" 문서에 명확히 기록됨

검증 명령:

```bash
.venv/bin/python -m compileall scripts llm
find orchestration -maxdepth 1 -type f | sort
.venv/bin/pytest tests -q
```

세션 종료 시 handoff에 반드시 적을 것:

- compileall failure 원인과 수정 방식
- 새 orchestration artifact 요약
- 남은 architecture gap

---

## 8. 세션 종료 시 handoff 공통 형식

각 세션 종료 시 아래 6가지는 반드시 남긴다.

1. 완료한 packet 이름
2. 실제 수정한 파일 목록
3. 통과한 검증 명령
4. 아직 남은 리스크 3개 이하
5. 다음 packet이 바로 이어받아야 할 포인트
6. live run 기준 성공/실패 여부와 실패 유형

---

## 9. 시작 packet 고정

다음 코딩 에이전트가 가장 먼저 시작할 packet은 아래로 고정한다.

- **WP-R1. Approval Canonicalization**

---

## 10. 2026-04-05 이후 addendum

이 문서의 `WP-R*` packet들은 **runtime recovery historical record**로 유지한다.

다음 조건 중 하나에 해당하면 packet 선택 기준은 이 문서가 아니라
`ORIGINAL_DESIGN_GAP_CLOSURE_PLAN.md`를 따른다.

1. 사용자가 original design, acceptance baseline, `purrfect-riding-blossom.md` 도달도를 묻는 경우
2. AUD-2에서 드러난 gap을 닫으라는 요청인 경우
3. 같은 프롬프트로 다음 세션을 계속 이어가고 싶은 경우

이 addendum 이후의 기본 규칙:

- 공통 필수 읽기에 `ORIGINAL_DESIGN_GAP_CLOSURE_PLAN.md`를 추가한다.
- 다음 세션은 해당 문서의 `DONE`이 아닌 가장 앞 packet 하나만 수행한다.
- 세션 종료 시 `IMPLEMENTATION_PROGRESS.md`와 `SESSION_LOG.md`에 original design cycle 상태를 반영한다.
