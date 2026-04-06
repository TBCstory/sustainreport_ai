# sustainreport-ai

ESG 지속가능경영보고서 초안 생성 시스템

## 개요

sustainreport-ai는 ESG 지속가능경영보고서 초안을 자동 생성하는 오케스트레이터 시스템입니다.
완전한 납품본을 만드는 것이 아니라, 컨설턴트가 검토·수정·템플릿 이관할 수 있는 **근거 기반 초안**을 생성합니다.

핵심 원칙:
- **불확실성을 숨기지 않는다** — 플레이스홀더, [확인필요] 표시, 낮은 신뢰도 경고는 초안의 정상적인 일부
- **증거 없으면 쓰지 않는다** — 출처 없는 문장, 임의 수치, 추정을 사실처럼 쓰는 것은 금지
- **통제 > 자동화** — 시스템이 제안하고, 사람이 결정

## 주요 기능

- **P0~P7 워크플로우**: 프로젝트 정의 → 자료 투입 → 기획 → 버킷 구축 → 초안 작성 → 검수 → 정리 → 증거 패키지
- **에이전트 기반 아키텍처**: data-analyst, toc-planner, section-writer, internal-reviewer, fact-checker, provenance-builder
- **프레임워크 매핑**: GRI, TCFD, KSSB 등 주요 ESG 프레임워크 지원
- **증거 기반 초안**: 모든 사실/수치에 출처 태그(provenance tag) 필수
- **게이트 기반 품질 관리**: P2→P3(blueprint 승인), P5→P6(검수 승인) 게이트

## 설치

```bash
# 의존성 설치
uv sync

# CLI 설치 확인
.venv/bin/sustainreport --help
```

## 빠른 시작

### 1. 프로젝트 초기화

```bash
sustainreport init-workspace PRJ-2026-0402-ESG001 --base-path ./workspaces
```

### 2. 자료 투입 (P1)

```bash
sustainreport run-ingestion workspaces/PRJ-2026-0402-ESG001
```

### 3. 기획 (P2)

```bash
sustainreport run-plan --workspace workspaces/PRJ-2026-0402-ESG001
```

### 4. 초안 작성 (P4)

```bash
# 전체 섹션
sustainreport run-draft --workspace workspaces/PRJ-2026-0402-ESG001

# 특정 섹션만
sustainreport run-draft --workspace workspaces/PRJ-2026-0402-ESG001 --section SEC-3.1
```

### 5. 상태 확인

```bash
sustainreport status --workspace workspaces/PRJ-2026-0402-ESG001
```

### 6. 게이트 승인

```bash
# P2→P3 게이트 승인
sustainreport approve P2_to_P3 --workspace workspaces/PRJ-2026-0402-ESG001 --by consultant_lead

# P5→P6 게이트 승인
sustainreport approve P5_to_P6 --workspace workspaces/PRJ-2026-0402-ESG001 --by consultant_lead
```

## 명령어 참조

### 프로젝트 관리

| 명령 | 설명 |
|------|------|
| `sustainreport init-workspace <project_id>` | 새 프로젝트 워크스페이스 생성 |
| `sustainreport status --workspace <path>` | 프로젝트 상태 요약 출력 |
| `sustainreport update-state --workspace <path>` | project_state.json 갱신 |

### 파이프라인

| 명령 | 설명 |
|------|------|
| `sustainreport run-pipeline --workspace <path> [--start P0] [--end P7]` | 전체/범위 파이프라인 실행 |
| `sustainreport run-ingestion <workspace>` | P1 자료 투입 |
| `sustainreport run-plan --workspace <path>` | P2 기획 |
| `sustainreport run-draft --workspace <path> [--section SEC-X.Y]` | P4 초안 작성 |

### 게이트 및 검수

| 명령 | 설명 |
|------|------|
| `sustainreport check-gate <gate> --workspace <path>` | 게이트 조건 평가 |
| `sustainreport approve <gate> --workspace <path> [--by <name>]` | 게이트 승인 기록 |

## 프로젝트 구조

```
workspaces/PRJ-YYYY-CODE-NNN/
  00_definition/           # 프로젝트 헌장, 이해관계자 매트릭스
  01_raw/                 # 원본 파일 (불변)
  02_file_registry/       # 파일 추적
  03_normalized_md/        # 정규화된 콘텐츠
  04_segments/            # 추출된 세그먼트
  05_planning/            # writing_blueprint, structure_index
  06_buckets/             # 섹션별 증거 버킷
  07_drafts/              # 초안 MD + 메타
  08_review/              # 검수 보고서
  09_handoff/             # 핸드오프 패키지 (draft_package.json, handoff_summary.md)
  10_evidence_pack/       # 감사 증거 패키지
  guidance/               # style_guide, terminology_dictionary
  context_bus/            # events.jsonl, runs.json, incidents.json
  draft_queries.json      # 초안 질문 트래커
  project_state.json      # 파생 상태 요약
  blocking_issues.json   # 차단 이슈
  next_actions.json      # 다음 행동 제안
  approval_gates.json     # 게이트 승인 상태
```

## 권장사항

- 증거 없는 수치나 사실을 생성하지 마세요
- LLM 할루시네이션을 초안에 포함하지 마세요
- 게이트를 임의로 건너뛰지 마세요
- 사람 승인 없이 blueprint를 변경하지 마세요
- JSON 파일을 직접 편집하지 말고 CLI 명령을 사용하세요

## 라이선스

MIT