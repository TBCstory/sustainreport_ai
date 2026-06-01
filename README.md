# sustainreport-ai

ESG 지속가능경영보고서 초안 생성 시스템

> Alpha-stage, consultant-in-the-loop, evidence-grounded draft generation

## 개요

sustainreport-ai는 ESG 지속가능경영보고서 초안을 자동 생성하는 오케스트레이터 시스템입니다. 완전한 납품본을 만드는 것이 아니라, 컨설턴트가 검토·수정·템플릿 이관할 수 있는 **근거 기반 초안**을 생성합니다.

핵심 원칙:

- **불확실성을 숨기지 않는다** — 플레이스홀더, `[확인필요]` 표시, 낮은 신뢰도 경고는 초안의 정상적인 일부
- **증거 없으면 쓰지 않는다** — 출처 없는 문장, 임의 수치, 추정을 사실처럼 쓰는 것은 금지
- **통제 > 자동화** — 시스템이 제안하고, 사람이 결정

## Why This Project Matters / 왜 이 프로젝트가 중요한가

지속가능경영보고서 작성은 단순한 문서 생성 문제가 아니라, 근거 정리, 프레임워크 매핑, 내부 검토, 사람 승인 흐름이 모두 얽힌 운영 문제에 가깝습니다.

이 프로젝트는 그 과정을 "최종 보고서 자동 작성"이 아니라 "검토 가능한 초안 생성"으로 좁혀 다룹니다. 즉, 컨설턴트가 다음 행동을 빠르게 판단할 수 있도록 구조화된 초안, 증거 버킷, 상태 요약, 승인 게이트를 제공하는 데 초점을 둡니다.

## Who This Is For / 누구를 위한 프로젝트인가

이 저장소는 다음과 같은 사용자와 기여자에게 적합합니다.

- ESG 지속가능경영보고서 초안 작성 파이프라인을 구조화하려는 컨설턴트와 PM
- GRI, TCFD, KSSB, ESRS 등 프레임워크 매핑 자동화를 다루려는 개발자
- 사람 승인과 증거 추적이 중요한 문서 오케스트레이션 워크플로우를 연구하는 기여자
- CLI 기반 오픈소스 도구의 품질, 테스트, 문서화를 개선하려는 유지보수 참여자

다음과 같은 목적에는 아직 적합하지 않습니다.

- 사람 검토 없이 최종 납품본을 바로 발행하는 자동화
- 프로덕션 검증이 끝난 엔터프라이즈 배포 도구

## 현재 상태

이 프로젝트는 현재 **alpha-stage** 입니다.

- 핵심 워크플로우와 CLI는 존재하지만, 공개 오픈소스 저장소로서의 문서화와 운영 안정성은 계속 정리 중입니다
- 프로덕션 레디를 주장하지 않습니다
- 공개 예시와 테스트는 비밀 데이터 없이 동작해야 하며, 실제 고객 자료는 저장소에 포함하지 않습니다

## 주요 기능

- **P0~P7 워크플로우**: 프로젝트 정의 → 자료 투입 → 기획 → 버킷 구축 → 초안 작성 → 검수 → 정리 → 증거 패키지
- **에이전트 기반 아키텍처**: `data-analyst`, `toc-planner`, `section-writer`, `internal-reviewer`, `fact-checker`, `provenance-builder`
- **프레임워크 매핑**: GRI, TCFD, KSSB 등 주요 ESG 프레임워크 지원
- **증거 기반 초안**: 모든 사실/수치에 출처 태그(provenance tag) 필수
- **게이트 기반 품질 관리**: P2→P3(blueprint 승인), P5→P6(검수 승인) 게이트

## 설치

```bash
# 기본 실행 환경
uv sync
uv run sustainreport --help
```

개발용 체크까지 포함해 설치하려면:

```bash
uv sync --extra dev
```

## 빠른 시작

### 1. 프로젝트 초기화

```bash
uv run sustainreport init-workspace PRJ-2026-0402-ESG001 --base-path ./workspaces
```

### 2. 자료 투입 (P1)

```bash
uv run sustainreport run-ingestion workspaces/PRJ-2026-0402-ESG001
```

### 3. 기획 (P2)

```bash
uv run sustainreport run-plan --workspace workspaces/PRJ-2026-0402-ESG001
```

### 4. 초안 작성 (P4)

```bash
# 전체 섹션
uv run sustainreport run-draft --workspace workspaces/PRJ-2026-0402-ESG001

# 특정 섹션만
uv run sustainreport run-draft --workspace workspaces/PRJ-2026-0402-ESG001 --section SEC-3.1
```

### 5. 상태 확인

```bash
uv run sustainreport status --workspace workspaces/PRJ-2026-0402-ESG001
```

### 6. 게이트 승인

```bash
# P2→P3 게이트 승인
uv run sustainreport approve P2_to_P3 --workspace workspaces/PRJ-2026-0402-ESG001 --by consultant_lead

# P5→P6 게이트 승인
uv run sustainreport approve P5_to_P6 --workspace workspaces/PRJ-2026-0402-ESG001 --by consultant_lead
```

추가 배경 문서는 [`docs/CONSULTANT_QUICKSTART.md`](docs/CONSULTANT_QUICKSTART.md)를 참고하세요.

## Open-Source Readiness / 기여 포인트

공개 기여는 다음 영역에서 특히 환영합니다.

- 버그 리포트와 재현 가능한 결함 수정
- README, 온보딩, 사용 예시, 구조 설명 개선
- 테스트 추가와 CI 안정화
- ESG 프레임워크 매핑 품질 개선
- CLI 사용성 개선과 상태 메시지 정리
- 이슈 트리아지와 최소 재현 케이스 정리

자세한 기여 방법은 [`CONTRIBUTING.md`](CONTRIBUTING.md)를 참고하세요.

## Roadmap

가까운 범위의 현실적인 개선 영역은 다음과 같습니다.

- 더 안정적인 CLI smoke test와 회귀 테스트 보강
- repository-wide Ruff 정리와 점진적인 lint 기준 확대
- 프레임워크 매핑 검증 규칙과 fixture 품질 개선
- 상태 요약, 게이트 안내, 핸드오프 산출물의 일관성 향상
- 공개 저장소에 적합한 synthetic/scrubbed 예제 자료와 문서 강화

이 목록은 방향성을 설명하기 위한 것으로, 완료를 보장하는 약속 목록은 아닙니다.

## Safety and Data Handling / 안전한 데이터 취급

이 저장소는 공개 오픈소스 저장소이므로 다음 원칙을 지켜야 합니다.

- 실제 API 키, 토큰, `.env` 파일을 커밋하지 않습니다
- 실제 고객 ESG 문서, 내부 보고서, 사적 워크스페이스를 커밋하지 않습니다
- `.env.example`에는 placeholder만 둡니다
- `workspaces/` 아래 생성 산출물은 비밀 정보를 포함할 수 있으므로 Git에서 제외합니다
- 테스트와 예시는 synthetic 또는 scrubbed 데이터만 사용합니다

보안 취약점이나 민감 데이터 노출 우려는 [`SECURITY.md`](SECURITY.md)를 따라 보고해 주세요.

## 명령어 참조

### 프로젝트 관리

| 명령 | 설명 |
|------|------|
| `sustainreport init-workspace <project_id>` | 새 프로젝트 워크스페이스 생성 |
| `sustainreport status --workspace <path>` | 프로젝트 상태 요약 출력 |
| `sustainreport update-state --workspace <path>` | `project_state.json` 갱신 |

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

```text
workspaces/PRJ-YYYY-CODE-NNN/
  00_definition/          # 프로젝트 헌장, 이해관계자 매트릭스
  01_raw/                 # 원본 파일 (불변)
  02_file_registry/       # 파일 추적
  03_normalized_md/       # 정규화된 콘텐츠
  04_segments/            # 추출된 세그먼트
  05_planning/            # writing_blueprint, structure_index
  06_buckets/             # 섹션별 증거 버킷
  07_drafts/              # 초안 MD + 메타
  08_review/              # 검수 보고서
  09_handoff/             # 핸드오프 패키지
  10_evidence_pack/       # 감사 증거 패키지
  guidance/               # style_guide, terminology_dictionary
  context_bus/            # events.jsonl, runs.json, incidents.json
  draft_queries.json      # 초안 질문 트래커
  project_state.json      # 파생 상태 요약
  blocking_issues.json    # 차단 이슈
  next_actions.json       # 다음 행동 제안
  approval_gates.json     # 게이트 승인 상태
```

## 권장사항

- 증거 없는 수치나 사실을 생성하지 마세요
- LLM 할루시네이션을 초안에 포함하지 마세요
- 게이트를 임의로 건너뛰지 마세요
- 사람 승인 없이 blueprint를 변경하지 마세요
- JSON 상태 파일을 직접 손대기보다 CLI와 스크립트를 우선 사용하세요

## Contributing / 기여

문서, 테스트, 버그 수정, 프레임워크 매핑 개선, CLI 사용성 개선, 이슈 트리아지를 포함한 기여를 환영합니다. 시작 전에는 [`CONTRIBUTING.md`](CONTRIBUTING.md)를 읽어 주세요.

## License / 라이선스

이 저장소는 MIT 라이선스를 따릅니다. 자세한 내용은 [`LICENSE`](LICENSE)를 참고하세요.
