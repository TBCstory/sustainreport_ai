# 구현 가이드 — Sonnet 참조용

## 현재 상태

완성된 것:
- `CLAUDE.md` — 오케스트레이터 헌법
- `agents/section-writer.md` — 에이전트 프롬프트 예시 (다른 에이전트의 설계 패턴)
- `schemas/writing_blueprint.schema.json` — writing_blueprint JSON Schema
- `schemas/structure_index.schema.json` — 구조 앵커 레지스트리 JSON Schema
- 디렉토리 구조 생성 완료 (agents/, orchestration/, schemas/, scripts/, llm/, templates/, .claude/agents/)

## PoC 구현 순서 (권장)

### Step 1: 프로젝트 초기화 인프라
1. `pyproject.toml` 작성 (Python 3.13, 의존성: markitdown, jsonschema, litellm)
2. `scripts/init_workspace.py` — 워크스페이스 디렉토리 구조 생성
3. `.gitignore` (workspaces/ 등)

### Step 2: 오케스트레이션 규칙 파일
1. `orchestration/phase_rules.json` — P0~P7 진입/종료 조건
2. `orchestration/gate_rules.json` — 자동 vs 사람 승인
3. `orchestration/agent_contracts.json` — 에이전트별 입출력
4. `orchestration/model_routing.json` — 역할별 모델 정책 (PoC는 Claude 단일)
5. `orchestration/agent_runtime_policy.json` — persistent/ephemeral

### Step 3: 핵심 스크립트
1. `scripts/log_event.py` — 이벤트 기록 (3종 로그 분리)
2. `scripts/check_gate.py` — 게이트 판정
3. `scripts/update_project_state.py` — 파생 상태 요약 갱신
4. `scripts/rebuild_summaries.py` — 요약 재구축
5. `scripts/normalize.py` — 파일 변환 (markitdown 래핑)

### Step 4: 나머지 에이전트 프롬프트
- `agents/data-analyst.md`
- `agents/toc-planner.md`
- `agents/framework-mapper.md`
- `agents/internal-reviewer.md`
- `agents/fact-checker.md`
- `agents/provenance-builder.md`

**패턴**: `agents/section-writer.md`를 참조. 모든 에이전트는 다음 구조:
- 역할 정의
- 입력 계약 (읽어야 할 파일 테이블)
- 출력 계약 (생성할 파일 + 형식)
- 작업 규칙 + 금지 사항
- 이벤트 기록 의무

### Step 5: 나머지 JSON Schema
- `schemas/draft_meta.schema.json`
- `schemas/draft_queries.schema.json`
- `schemas/section_bucket.schema.json`
- `schemas/kpi_registry.schema.json`
- `schemas/framework_index.schema.json`
- `schemas/file_registry.schema.json`

### Step 6: LLM 래퍼
- `llm/router.py` — litellm 래퍼 + model_routing.json 참조 + 실행 기록
- `llm/call_log.py` — 실행 기록 저장

### Step 7: Claude Code 어댑터
- `.claude/agents/*.md` — agents/를 참조하는 래퍼

## 기술 결정 요약

| 항목 | 결정 |
|------|------|
| Python | 3.13 (`/opt/homebrew/bin/python3.13`) |
| 패키지 관리 | uv + pyproject.toml |
| 계약 정의 | JSON Schema (`schemas/*.schema.json`) |
| LLM 호출 | litellm (멀티모델 통합) |
| 파일 변환 | markitdown |
| DOCX 생성 | python-docx (후순위) |
| HWP 파싱 | pyhwp 또는 hwp5 (조사 후 결정) |

## 에이전트 프롬프트 설계 원칙

1. **런타임 중립**: agents/*.md는 특정 LLM이나 프레임워크에 종속되지 않음
2. **입출력 계약 명시**: 읽을 파일과 생성할 파일을 테이블로 명시
3. **일관성 계약 주입**: style_guide, terminology_dictionary, writing_blueprint 참조를 필수로 명시
4. **불확실성 처리**: 증거 없으면 쓰지 않는 규칙을 모든 에이전트에 명시
5. **이벤트 기록 의무**: 작업 완료 후 log_event.py 호출을 필수로 명시

## 상세 설계 문서

전체 아키텍처 플랜: `/Users/lj_homemac/.claude/plans/purrfect-riding-blossom.md`
