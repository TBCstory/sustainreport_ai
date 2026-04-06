# Original Design Gap Closure Plan

작성일: 2026-04-05

이 문서는 `purrfect-riding-blossom.md`를 acceptance baseline으로 삼아, AUD-2에서 드러난 **원 설계 대비 미도달 gap**을 순차적으로 닫기 위한 실행 계획서다.

중요:

- 이 문서는 "테스트가 통과하는가?"보다 **"최초 설계 목표에 실제 도달했는가?"**를 우선한다.
- 기존 `WP-R*`, `EG-*`, `HO-*`, `E2E-*`는 **runtime recovery 기록**으로 유지한다.
- 다음 세션부터는 **같은 프롬프트를 반복 사용**해도 된다. 에이전트는 이 문서에서 `DONE`이 아닌 가장 앞 packet 하나만 수행한다.
- packet 완료와 원 설계 도달은 분리해서 적는다.

---

## 1. Baseline과 목표

기준 문서:

- `purrfect-riding-blossom.md`
- 특히 아래 acceptance-critical 영역
  - 시스템 목표
  - TOC/Blueprint 계약
  - Writer/meta/query 계약
  - Bucket 구조 계약
  - 자연어 UX 목표
  - 핵심 설계 결정 요약
  - E2E acceptance 시나리오

이번 cycle의 최종 목표:

1. **근거 기반 초안 생성 시스템**으로 실제 동작한다.
2. **자연어 오케스트레이터 + 파일 기반 진실의 원천 + 게이트 discipline**이 구현물에서 드러난다.
3. **불확실성 노출 / consultant next action / structure anchor / provenance / handoff** 계약이 산출물에 반영된다.
4. exact fresh lane과 final acceptance audit을 다시 돌렸을 때, runtime 성공과 설계 도달도 평가가 서로 크게 어긋나지 않는다.

---

## 2. AUD-2에서 확인된 핵심 gap 묶음

### A. Exact fresh primary lane gap

- `init-workspace`만으로는 P0 산출물이 준비되지 않아 exact lane이 P0에서 멈춘다.
- `run-plan`은 300초 polling으로 막혀 자연어 승인 UX 대신 장시간 block을 만든다.
- 일부 CLI 경로는 실패했는데도 process exit/result story가 혼동을 준다.

### B. Grounded bucket / grounded draft gap

- sample fresh lane에서 `segment_manifest`는 1개 세그먼트를 만들었지만 mapper가 bucket에 연결하지 못했다.
- 그 결과 16/16 bucket이 empty, 16/16 draft가 fallback-only였다.
- 즉, 현재 구현은 "초안을 만든다"보다 "placeholder package를 만든다"에 가깝다.

### C. Contract integrity gap

- `manual` 섹션이 자동 draft 대상에 들어간다.
- `SUB-SEC-*`가 planning에는 존재하지만 bucket/draft/state 경로에서 탈락한다.
- `draft_queries.json`는 병렬 실행에서 누락될 수 있다.

### D. State / handoff / indexing gap

- pipeline 완료 후에도 `blocking_issues.json`, `next_actions.json`가 stale할 수 있다.
- handoff는 placeholder count는 보여주지만 unresolved query, missing_evidence, client_confirmation_needed, source_conflicts를 충분히 싣지 않는다.
- `framework_indexing_readiness.json`가 없다.

### E. Natural-language orchestrator UX gap

- 현재 표면은 CLI 중심이며, 설계가 요구한 자연어 상태 보고/다음 행동 3개 이하 제안/blueprint 검토 UX가 canonical helper 없이 암묵적이다.

---

## 3. 세션 고정 프롬프트

다음 세션부터는 아래 프롬프트를 그대로 복붙해도 된다.

```text
sustainreport_ai original design gap closure 세션을 시작합니다.

중요 기준:
- acceptance baseline은 최신 remediation 로그가 아니라 /Users/lj_homemac/tools/sustainreport_ai/purrfect-riding-blossom.md 입니다.
- 이번 세션 목표는 ORIGINAL_DESIGN_GAP_CLOSURE_PLAN.md 에서 아직 DONE이 아닌 가장 앞 packet 하나만 수행하는 것입니다.
- packet 완료와 원 설계 도달도는 분리해서 기록하세요.

반드시 먼저 읽을 파일:
1. /Users/lj_homemac/tools/sustainreport_ai/AGENTS.md
2. /Users/lj_homemac/tools/sustainreport_ai/CLAUDE.md
3. /Users/lj_homemac/tools/sustainreport_ai/GAP_REMEDIATION_UPDATE_PLAN.md
4. /Users/lj_homemac/tools/sustainreport_ai/IMPLEMENTATION_EXECUTION_DIRECTIVES.md
5. /Users/lj_homemac/tools/sustainreport_ai/IMPLEMENTATION_PROGRESS.md
6. /Users/lj_homemac/tools/sustainreport_ai/ORIGINAL_DESIGN_GAP_CLOSURE_PLAN.md
7. /Users/lj_homemac/tools/sustainreport_ai/SESSION_LOG.md

그리고 ORIGINAL_DESIGN_GAP_CLOSURE_PLAN.md 에서 선택된 packet의 필수 읽기 파일만 추가로 읽으세요.

세션 규칙:
- 한 세션에서 packet 하나만 수행
- packet acceptance criteria를 충족할 때만 DONE
- 세션 종료 시 IMPLEMENTATION_PROGRESS.md 와 SESSION_LOG.md 를 반드시 갱신

세션 종료 시 반드시 남길 것:
- 수행한 packet 이름
- 실제 수정 파일
- 검증 명령과 결과
- exact fresh lane / assisted lane 여부
- packet 완료 여부
- 원 설계 기준 아직 남은 gap 3개 이하
- 다음 packet
```

---

## 4. 운영 규칙

### 4.1 packet 선택 규칙

- 항상 `DONE`이 아닌 **가장 앞 packet 하나만** 수행한다.
- 새 gap이 생겨도 packet 순서를 뒤집지 않는다.
- 기존 packet을 쪼개야 하면 `OD-xA`, `OD-xB`로 현재 packet 바로 뒤에 추가한다.

### 4.2 완료 판정 규칙

- test pass만으로는 완료가 아니다.
- packet마다 **runtime acceptance + design acceptance**를 모두 충족해야 한다.
- 한 packet에서 나온 부수 발견이 다음 packet의 핵심이면 handoff로 넘긴다.

### 4.3 문서 갱신 규칙

- `IMPLEMENTATION_PROGRESS.md`: packet 상태 표 + latest handoff 갱신
- `SESSION_LOG.md`: 실제 세션 결과 append
- packet이 새로 분화되면 이 문서의 status table부터 갱신

---

## 5. Packet Status

| Packet | 이름 | 상태 | 목적 |
|-------|------|------|------|
| OD-1 | Fresh Primary Lane and Exit Semantics Recovery | DONE | `run-plan` 폴링 제거 + 즉시 반환 (exit code 2, waiting). `init-workspace` P0 파일 자동 생성. CLI exit code 전파 수정. |
| OD-2 | Blueprint Hard Gate and Structure Stability | DONE | P3/P4 direct entry gate bypass 차단 + `verify_structure_stability()` helper + `_check_entry_conditions()` 추가. |
| OD-3 | Segment-to-Bucket Grounding Recovery | DONE | `_find_segments_for_section` 수정 — heading_path 문자열 처리 + segment content 직접 읽기 + keyword matching. bucket routing_reason/confidence_score/evidence_unit_type/evidence_binding_mode 메타데이터 추가. |
| OD-4 | Writer Contract / Manual / SUB-SEC Closure | DONE | `load_section_manifest()`/`is_manual_section()` — manual 섹션 자동 draft 제외. `_is_fallback_bucket()`/`_generate_fallback_draft()` 폴백 경로. 모든 draft meta 필드 완전 채움. |
| OD-5 | Draft Query and Summary Canonicalization | DONE | `FileLock` 기반 `_locked_draft_queries_update()` — 병렬 drafting race condition 해결. pipeline 완료 후 `rebuild_blocking_issues()`/`rebuild_next_actions()` 자동 호출. |
| OD-6 | Handoff / Indexing / Provenance Readiness Closure | DONE | `build_framework_indexing_readiness()` — `framework_indexing_readiness.json` 생성. handoff draft_package에 evidence metadata 배열 완전 채움. provenance metadata에 grounded/fallback mode 명시적 구분. |
| OD-7 | Natural-Language Orchestrator UX Surface | DONE | `generate_narrative_status()` 신규 — 자연어 상태 요약 (current phase, blockers, open queries, next actions ≤3, blueprint approval status). `cmd_status`가 이 helper 사용. |
| OD-8 | Original Design Final Acceptance Rerun | DONE | AUD-2 기준 재검수 완료 — 7개 항목 평가, critical 3개 모두 "Mostly Reached" 이상. Original Design Gap Closure Cycle 완료. |
| OD-9 | Source Tag Enforcement and Provenance Grounding | DONE | `validate_and_enforce_source_tags()` + `_find_untagged_sentences()` + `_register_source_tag_violations()` 신규. grounded draft에서 태그 없는 문단 자동 DQ 등록 (`query_type: source_tag_violation`). `write_single_section()`에 enforcement hook 추가. test regression 통과. |
| OD-10 | Provenance Paragraph Map and KPI Registry Foundation | DONE | `_build_paragraph_provenance_map()` + `_build_kpi_registry()` + OD-10 단위 테스트 12개 (`tests/test_run_framework_mapper.py`) 신규. 3경로(fallback/success/failure) 모두에서 `paragraph_provenance_map.json`/`kpi_registry.json` 생성. `kpi_registry.json`: 수치 추출 + evidence 연결 + `data_status` (confirmed/provisional/unresolved) 부여. routing logic 검증 완료. |

상태 값:

- `TODO`
- `IN_PROGRESS`
- `DONE`
- `BLOCKED`

---

## 6. Ordered Packets

### OD-1. Fresh Primary Lane and Exit Semantics Recovery

목표:

- 사용자가 요구한 exact fresh lane을 manual seeding 없이 다시 성립시킨다.
- `run-plan`이 blueprint review/approval 대기 상태를 **즉시 반환하는 UX**로 동작하게 만든다.
- CLI failure/success/approval-waiting exit semantics를 명확히 한다.

필수 읽기 파일:

- `scripts/init_workspace.py`
- `llm/cli.py`
- `scripts/run_pipeline.py`
- `scripts/run_toc_planner.py`
- `tests/test_run_toc_planner.py`
- `purrfect-riding-blossom.md`의 시스템 목표, 자연어 UX, E2E acceptance 시나리오

핵심 수정 범위:

- `scripts/init_workspace.py`
- `llm/cli.py`
- `scripts/run_pipeline.py`
- `scripts/run_toc_planner.py`
- 필요 시 `tests/test_run_toc_planner.py`
- 필요 시 신규 테스트 1개

완료 기준:

1. exact fresh lane
   - `init-workspace`
   - `run-ingestion`
   - `run-plan`
   - `run-pipeline --skip-approvals`
   - `update-state`
   - `status`
   - `run-pipeline --dry-run`
   - `check-gate`
   가 manual file seeding 없이 실행 가능해야 한다.
2. `run-plan`은 300초 polling block 대신
   - 산출물 저장
   - approval pending 상태 기록
   - 다음 행동 안내
   로 즉시 반환해야 한다.
3. CLI exit code가 실제 success/failure/waiting story와 맞아야 한다.

검증:

```bash
.venv/bin/sustainreport init-workspace PRJ-2026-OD1-FRESH --base-path ./workspaces
cp workspaces/PRJ-2026-TST-003/01_raw/test_report.txt workspaces/PRJ-2026-OD1-FRESH/01_raw/test_report.txt
.venv/bin/sustainreport run-ingestion workspaces/PRJ-2026-OD1-FRESH
.venv/bin/sustainreport run-plan --workspace workspaces/PRJ-2026-OD1-FRESH
.venv/bin/sustainreport run-pipeline --workspace workspaces/PRJ-2026-OD1-FRESH --skip-approvals
```

### OD-2. Blueprint Hard Gate and Structure Stability

목표:

- approved blueprint 없이 P3/P4로 들어갈 수 없게 한다.
- blueprint 수정 후 `section_id`, `heading_anchor`, `toc_path` 안정성을 테스트 가능한 helper로 고정한다.

필수 읽기 파일:

- `scripts/run_pipeline.py`
- `scripts/check_gate.py`
- `scripts/run_framework_mapper.py`
- `scripts/run_section_writer.py`
- `orchestration/phase_rules.json`
- `orchestration/gate_rules.json`
- `workspaces/PRJ-2026-TST-003/05_planning/structure_index.json`

핵심 수정 범위:

- `scripts/run_pipeline.py`
- `scripts/check_gate.py`
- planning 관련 구조 helper 신규/수정
- 관련 테스트 1~2개

완료 기준:

1. `--start P3` 같은 direct entry도 gate를 우회하지 못한다.
2. `skip-approvals`는 canonical approval 기록을 남기되, non-test path의 hard gate는 유지한다.
3. blueprint 수정 helper 또는 canonical regeneration 경로가 `section_id`, `heading_anchor`, `toc_path` 안정성을 보장한다.

### OD-3. Segment-to-Bucket Grounding Recovery

목표:

- sample fresh lane에서 최소 일부 섹션이라도 실제 세그먼트가 bucket에 라우팅되도록 만든다.
- bucket이 설계 문서의 라우팅 semantics를 더 많이 담도록 확장한다.

필수 읽기 파일:

- `scripts/run_ingestion.py`
- `scripts/run_framework_mapper.py`
- `workspaces/PRJ-2026-TST-003/01_raw/test_report.txt`
- `purrfect-riding-blossom.md`의 bucket 구조 계약

핵심 수정 범위:

- `scripts/run_ingestion.py`
- `scripts/run_framework_mapper.py`
- 필요 시 bucket schema/fixture 테스트

완료 기준:

1. fresh sample lane에서 evidence-bearing sections는 non-empty bucket을 가진다.
2. bucket은 empty/grounded/fallback 구분이 명확하다.
3. bucket metadata에 최소한 routing reason, confidence, evidence semantics가 살아 있다.

검증:

```bash
.venv/bin/python - <<'PY'
import json, pathlib
ws = pathlib.Path('workspaces/PRJ-2026-OD3-FRESH')
buckets = [json.loads(p.read_text()) for p in (ws/'06_buckets').glob('SEC-*.json')]
print(sum(1 for b in buckets if b.get('segments')))
PY
```

### OD-4. Writer Contract / Manual / SUB-SEC Closure

목표:

- grounded bucket은 실제 provenance-tagged draft를 만들고, manual section은 자동 draft에서 제외한다.
- `SUB-SEC-*`를 planning → bucket → draft → handoff까지 유지한다.

필수 읽기 파일:

- `scripts/run_section_writer.py`
- `scripts/update_project_state.py`
- `tests/test_run_section_writer.py`
- `purrfect-riding-blossom.md`의 writer/meta/query 계약

핵심 수정 범위:

- `scripts/run_section_writer.py`
- `scripts/update_project_state.py`
- 관련 테스트

완료 기준:

1. `manual` 섹션은 자동 draft 대상이 아니다.
2. `SUB-SEC-*`가 draft/handoff/state에서 탈락하지 않는다.
3. grounded draft에는 실제 `<!-- src:SEG-... -->` linkage가 들어간다.
4. draft meta 필수 필드
   - `draft_confidence`
   - `missing_evidence`
   - `client_confirmation_needed`
   - `source_conflicts`
   - `placeholders_inserted`
   가 fallback/grounded 경로 모두에서 안정적으로 채워진다.

### OD-5. Draft Query and Summary Canonicalization

목표:

- `draft_queries.json` 누락을 막고, state summaries가 실제 산출물과 자동으로 다시 맞춰지게 한다.

필수 읽기 파일:

- `scripts/run_section_writer.py`
- `scripts/rebuild_summaries.py`
- `scripts/update_project_state.py`
- `llm/cli.py`
- `tests/test_state_consistency.py`

핵심 수정 범위:

- `scripts/run_section_writer.py`
- `scripts/rebuild_summaries.py`
- `llm/cli.py`
- 필요 시 `scripts/run_pipeline.py`
- 관련 테스트

완료 기준:

1. parallel drafting에서도 placeholder query 누락이 없다.
2. pipeline 완료 후 `blocking_issues.json`, `next_actions.json`가 stale 상태에 머물지 않는다.
3. `status`는 top 3 next actions를 실제 state source에 맞게 보여준다.

### OD-6. Handoff / Indexing / Provenance Readiness Closure

목표:

- P6/P7 산출물이 consultant handoff와 indexing 준비 상태를 실제로 보여주게 만든다.

필수 읽기 파일:

- `scripts/run_handoff.py`
- `scripts/run_provenance_builder.py`
- `purrfect-riding-blossom.md`의 handoff/indexing/E2E acceptance 시나리오

핵심 수정 범위:

- `scripts/run_handoff.py`
- `scripts/run_provenance_builder.py`
- 필요 시 신규 readiness builder/helper
- 관련 테스트

완료 기준:

1. handoff package에 unresolved draft queries, placeholders, missing_evidence, client_confirmation_needed, source_conflicts가 반영된다.
2. `framework_indexing_readiness.json`가 생성된다.
3. evidence pack은 grounded trace와 fallback limitation을 구분해 표현한다.

### OD-7. Natural-Language Orchestrator UX Surface

목표:

- AI 세션이 stable하게 사용할 수 있는 **narrative helper**를 제공한다.
- 상태 설명, 다음 행동 3개 이하 제안, blueprint review summary를 canonical 형태로 만든다.

필수 읽기 파일:

- `AGENTS.md`
- `CLAUDE.md`
- `llm/cli.py`
- `scripts/update_project_state.py`
- `scripts/rebuild_summaries.py`
- `purrfect-riding-blossom.md`의 자연어 UX 목표

핵심 수정 범위:

- orchestrator narrative helper 신규/수정
- `llm/cli.py` 또는 helper consumer
- 관련 테스트 또는 snapshot

완료 기준:

1. 상태 질의용 canonical helper가
   - current phase
   - blockers
   - open queries
   - next actions 3개 이하
   를 자연어 블록으로 생성한다.
2. blueprint review/approval 상태를 사람이 이해하기 쉽게 설명할 수 있다.
3. CLI는 유지하되, AI 세션이 재사용할 수 있는 stable surface가 생긴다.

### OD-8. Original Design Final Acceptance Rerun

목표:

- AUD-2를 같은 baseline으로 다시 수행해 closeout 판단을 내린다.

필수 읽기 파일:

- `ORIGINAL_DESIGN_GAP_CLOSURE_PLAN.md`
- `IMPLEMENTATION_PROGRESS.md`
- `SESSION_LOG.md`
- `purrfect-riding-blossom.md`의 acceptance-critical 섹션

완료 기준:

1. exact fresh primary lane 결과를 다시 기록한다.
2. 아래 7개 항목을 다시 4단계로 평가한다.
   - system-goal fit
   - natural-language orchestration UX
   - blueprint gate discipline
   - evidence bucket contract
   - writer contract
   - handoff/indexing readiness
   - end-to-end reproducibility
3. critical 항목
   - evidence bucket contract
   - writer contract
   - blueprint gate discipline
   는 최소 `Mostly Reached` 이상이어야 closeout 가능하다.
4. 미달이면 새 packet을 정의하고 이 문서를 갱신한다.

### OD-9. Source Tag Enforcement and Provenance Grounding

목표:

1. **`<!-- src:SEG-XXXXX -->` 태그 강제 enforcement** — section-writer의 grounded 경로에서 LLM 응답이 provenance 태그를 포함하지 않으면 **자동 플래그 + 메타 필드에 기록**
2. **Grounded bucket E2E 검증** — OD-3에서 구현한 routing logic이 실제로 segments를 버킷에 연결하는지 검증

완료 기준:

1. grounded draft의 모든 문장에 `<!-- src:SEG-` 또는 `<!-- src:CALC-` 태그가 있거나, 없다면 `draft_meta.source_conflicts`에 해당 문장이 명시적으로 기록된다.
2. provenance 태그 없는 문장이 자동으로 `draft_queries.json`에 DQ-*로 등록된다.
3. OD-3 버킷 라우팅이 **최소 1개 섹션**에서 non-empty bucket을 만드는 것을 검증한다.

---

### OD-10. Provenance Paragraph Map and KPI Registry Foundation

목표:

1. **`paragraph_provenance_map.json` 생성** — §3.3 설계에 따른 문단 단위 provenance 추적. OD-9 enforcement의 `_find_untagged_sentences()` 결과를 활용하여 문단-세그먼트 매핑을 체계화
2. **KPI registry foundation** — §2.6/§3.1 설계에 따른 `kpi_registry.json` 구조 생성. 현재 `kpi_status_summary` 단순 추정을 evidence 기반 근사치로 보강
3. **Bucket routing logic 단위 테스트** — OD-3 `_find_segments_for_section()`의 라우팅 결과를 검증하는 unit test로, test data limitation에도 불구하고 logic correctness 확인

필수 읽기 파일:

- `scripts/run_section_writer.py` — 특히 OD-9 enforcement section, `_find_untagged_sentences()`, `validate_and_enforce_source_tags()`
- `scripts/run_framework_mapper.py` — 특히 `_find_segments_for_section()`, bucket status 결정
- `purrfect-riding-blossom.md` §3.3 Provenance Dual-Track ("문단 추적 — 전체 문단 대상"), §2.6 KPI 잠정 수치 상태 관리
- `schemas/kpi_registry.schema.json` — KPI registry 스키마 (존재 시)

핵심 수정 범위:

1. **`scripts/run_section_writer.py`** 또는 **`scripts/run_provenance_builder.py`** — `paragraph_provenance_map.json` 생성:
   - 각 draft 문단별 `<!-- src:SEG-... -->` 태그 presence를 기반으로 문단-세그먼트 매핑 생성
   - OD-9 `_find_untagged_sentences()` 결과를 재활용하여 태그 없는 문단도 명시적으로 기록
   - §3.3 설계의 경량 문단 추적 요구 충족
2. **`scripts/run_provenance_builder.py`** 또는 **`scripts/run_handoff.py`** — `kpi_registry.json` 생성:
   - draft 내 수치mention을 추출하고 src 태그 기반으로 evidence 연결
   - 각 KPI별 `data_status` (confirmed/provisional/unresolved) 부여
   - `kpi_status_summary` 단순 추정을 근사적으로 보강
3. **`tests/test_run_framework_mapper.py`** — `_find_segments_for_section()`의 routing logic 단위 테스트 (multi-segment fixture 사용)

완료 기준:

1. `paragraph_provenance_map.json`이 생성되어 draft당 문단 수, 태그 coverage, 태그 없는 문단 목록을 포함한다.
2. `kpi_registry.json`이 생성되어 draft 내 발견된 수치를 evidence segment와 연결하고 `data_status`를 부여한다.
3. `_find_segments_for_section()`의 라우팅 logic이 단위 테스트에서 올바른 segment를 매칭함을 증명한다.

---

## 7. 프로그램 전체 완료 기준

아래가 모두 충족되면 original design gap closure cycle을 종료할 수 있다.

1. exact fresh primary lane이 manual seeding 없이 재현된다.
2. sample fresh lane에서 **실제 grounded bucket과 grounded draft**가 확인된다.
3. manual / SUB-SEC / structure anchor contract가 end-to-end로 유지된다.
4. draft_queries, blocking_issues, next_actions, status가 같은 현실을 설명한다.
5. handoff package와 indexing readiness artifact가 consultant next action을 명확히 보여준다.
6. final acceptance audit에서 packet 완료와 원 설계 도달도 사이의 큰 차이가 해소된다.

---

## 8. 세션 종료 공통 형식

각 세션 종료 시 아래 7가지를 반드시 남긴다.

1. 수행한 packet 이름
2. 실제 수정 파일 목록
3. 통과한 검증 명령
4. exact fresh lane / assisted lane / seeded lane 여부
5. packet 완료 여부
6. 원 설계 기준 아직 남은 gap 3개 이하
7. 다음 packet
