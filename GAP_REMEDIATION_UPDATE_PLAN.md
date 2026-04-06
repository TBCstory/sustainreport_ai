# Gap Remediation Update Plan

작성일: 2026-04-03

## 1. 목적

이번 업데이트 계획의 목적은 다음 두 가지를 동시에 달성하는 것이다.

1. 설계 의도대로 오케스트레이터가 실제로 동작하도록 런타임/계약 gap을 해소한다.
2. ESG 보고서 초안을 작성하는 실무 컨설턴트가 "더미 자료를 받고, 맡은 섹터/섹션의 초안을 빠르게 만든 뒤, 추가 확인사항을 정리하는" 실제 업무 흐름에서 사용할 수 있도록 사용성을 보완한다.

핵심 원칙:

- 최종 납품본이 아니라 근거 기반 초안을 만드는 시스템이라는 포지션은 유지한다.
- 증거 부족, 승인 필요, 미확인 사항은 숨기지 않고 명시한다.
- "파일 기반 PoC"를 먼저 안정화하고, 그 다음에 인터페이스를 얹는다.
- 컨설턴트는 JSON 파일을 직접 편집하는 사람이 아니라, 초안과 액션 아이템을 소비하는 사용자로 본다.

## 2. 목표 사용 형태 재정의

현재 시스템은 사실상 "개발자/AI 운영자용 저장소 내부 CLI"에 가깝다. 업데이트 후의 목표 사용 형태는 아래와 같이 정의한다.

### 2.1 단기 목표 사용 형태

- 실행 위치: 로컬 저장소 또는 내부 실행 환경의 터미널
- 주 사용자:
  - 오케스트레이터 운영자: 프로젝트 초기화, ingestion, planning, gate 처리, 전체 상태 확인
  - 섹션 담당 컨설턴트: 자신이 맡은 섹션만 draft 재생성, open query 확인, 근거 부족 영역 파악
  - 리뷰어/리드: 승인, blocking issue 확인, handoff 판단
- 사용 인터페이스:
  - 안정적인 CLI 명령
  - 사람이 읽을 수 있는 markdown/json 산출물
  - JSON 직접 편집 대신 명시적 approve/status 명령

### 2.2 중기 목표 사용 형태

- 실행 위치: 동일한 저장소 기반
- 추가 인터페이스:
  - lightweight local dashboard 또는 TUI
  - 섹션별 작업 패키지/요약 화면
- 단, 웹앱 구축은 본 단계의 선행조건이 아니다.

## 3. 해결해야 할 gap 묶음

### A. 런타임 안정성 gap

- 승인 게이트가 실제로 동작하지 않음
- P2 산출물 생성 방식이 설계 계약과 불일치
- 패키지 CLI 엔트리포인트가 깨져 있음
- multi-file ingestion 시 segment/provenance 충돌 가능
- 중첩 raw 폴더를 기본 수집하지 못함

### B. 오케스트레이션/상태 gap

- `project_state.json`, `blocking_issues.json`, `next_actions.json`의 신뢰도가 낮음
- manual 섹션과 자동 섹션 구분이 상태 계산에 충분히 반영되지 않음
- draft query와 blocking issue가 일관된 작업 큐로 연결되지 않음

### C. 컨설턴트 실무 flow gap

- "내 섹션만 돌려보기" 전까지 필요한 준비가 많음
- placeholder와 추가 요청 사항이 초안 후속 작업으로 잘 정리되지 않음
- 근거 부족, 숫자 미확정, 리드 승인 필요 여부가 한눈에 보이지 않음
- 산출물이 markdown/json 위주라서 실무자가 바로 리뷰하기에 다소 거칠다

### D. 제품화 gap

- 현재는 내부 PoC 실행 스크립트 모음이지, 명확한 제품 진입점이 아님
- 승인/상태/섹션 작업이 파일 편집 관행에 의존함
- onboarding 문서와 happy path 예제가 부족함

## 4. 업데이트 전략

업데이트는 아래 4개 workstream으로 진행한다.

1. Foundation Stabilization
2. Consultant Workflow Enablement
3. State / Review / Approval Hardening
4. Packaging and Pilot Readiness

우선순위 원칙:

- 1순위: 전체 파이프라인이 깨지지 않게 만드는 작업
- 2순위: 섹션 담당 컨설턴트가 실제로 초안을 만들 수 있게 하는 작업
- 3순위: 상태/승인/핸드오프를 믿고 운영할 수 있게 만드는 작업
- 4순위: 사용 진입점과 문서를 정리하는 작업

## 5. Workstream별 계획

### WS-1. Foundation Stabilization

목표:

- 설계된 P0-P7 파이프라인이 기본 happy path에서 실제 동작하도록 만든다.

주요 작업:

- 승인 게이트 import 및 승인 상태 표현을 단일 방식으로 정리
- `run_toc_planner.py`의 P2 순서를 "생성 -> 저장 -> 승인 대기"로 수정
- P2 다중 산출물 처리를 위한 structured output 파서 도입
- CLI 엔트리포인트를 실제 존재하는 모듈/명령으로 교정
- ingestion의 재귀 파일 수집 지원
- workspace 전역 segment ID 발급기 도입
- 기본 E2E smoke test를 nested raw 폴더 기준으로 추가

산출물:

- 안정화된 phase runner
- 통합 CLI 진입점
- multi-file safe ingestion
- 게이트 동작 테스트

완료 기준:

- nested raw 자료가 있는 테스트 workspace에서 P1-P3까지 성공
- 승인 게이트가 실제로 waiting -> approved -> passed로 진행
- `sustainreport --help`가 정상 동작
- 여러 파일 ingestion 후 segment ID/provenance가 충돌하지 않음

### WS-2. Consultant Workflow Enablement

목표:

- "담당 섹터/섹션을 맡은 실무자"가 더미 자료 기반 초안 작성 업무를 실제로 수행할 수 있게 한다.

주요 작업:

- section-level happy path 정의:
  - `init`
  - `ingest`
  - `plan`
  - `draft --section SEC-X.Y`
  - `status --section SEC-X.Y`
- `section-writer` 결과에서 draft meta와 draft queries를 안정적으로 분리/기록
- placeholder 삽입 시 `draft_queries.json` append/update 로직 구현
- 섹션별 "작업 패키지" 생성:
  - 현재 초안
  - open query
  - missing evidence
  - source tag 수
  - confidence
- manual/rigid/flex 모드별 작업자 경험 차등화
- 섹션 재실행 시 기존 draft/query/meta와 충돌 없이 갱신되도록 설계

산출물:

- 섹션 담당자용 실행 명령
- 섹션 작업 패키지 JSON/Markdown
- draft query append/update 로직

완료 기준:

- 실무자가 `--section` 한 번으로 자신의 섹션 초안을 생성/재생성 가능
- 초안에 생긴 placeholder가 open query로 누락 없이 기록
- 실무자가 "추가 요청해야 할 자료"를 파일 1-2개만 보고 바로 파악 가능

### WS-3. State / Review / Approval Hardening

목표:

- 오케스트레이터가 상태를 믿고 다음 행동을 제안할 수 있게 만든다.

주요 작업:

- `update_project_state.py`에서 manual section 제외/반영 규칙 명확화
- `rebuild_summaries.py`의 ID 중복, 상태 덮어쓰기, 출력 정합성 수정
- `blocking_issues.json`와 `next_actions.json`를 canonical summary로 재정의
- draft query, review report, blocking issue 간 상호 링크 추가
- 승인 명령 추가:
  - `approve --gate P2_to_P3`
  - `approve --gate P5_to_P6`
- `status` 출력 개선:
  - 현재 phase
  - top blockers
  - open draft queries
  - 재작업 필요한 섹션

산출물:

- 신뢰 가능한 상태 요약 파일
- 승인 명령
- 운영자/리드용 상태 요약 출력

완료 기준:

- 상태 파일과 실제 산출물 간 불일치가 없어야 함
- `next_actions.json`의 ID와 액션 수가 안정적이어야 함
- 오케스트레이터가 JSON 원문을 열지 않고도 다음 행동 3개 이하를 제안할 수 있어야 함

### WS-4. Packaging and Pilot Readiness

목표:

- 내부 파일 기반 PoC를 "팀이 써볼 수 있는 도구"로 끌어올린다.

주요 작업:

- README를 실제 사용 흐름 기준으로 재작성
- 섹션 담당 컨설턴트용 quickstart 추가
- dummy workspace 기반 end-to-end demo 시나리오 정리
- handoff 패키지에 실무 친화적인 summary markdown 추가
- 필요 시 lightweight local dashboard/TUI 초안 도입
- 운영상 비추 경로 명시:
  - JSON 직접 편집 금지
  - 승인 파일 수동 수정 최소화

산출물:

- 운영 문서
- quickstart
- pilot demo workflow

완료 기준:

- 신규 사용자도 문서만 보고 sample workspace를 한 번 실행할 수 있어야 함
- 섹션 담당 컨설턴트가 자신의 섹션 draft와 open issue를 10분 내 파악 가능해야 함

## 6. 실행 순서

### Phase 1. Runtime Recovery

- WS-1의 게이트/CLI/P2/ingestion 핵심 수정
- 기간 추정: 2-4일

### Phase 2. Section Assignee Loop

- WS-2 중심
- 기간 추정: 3-5일

### Phase 3. State and Review Reliability

- WS-3 중심
- 기간 추정: 2-3일

### Phase 4. Pilot Packaging

- WS-4 중심
- 기간 추정: 1-2일

## 7. 우선 구현 backlog

### Priority 0

- 게이트 승인 경로 복구
- P2 다중 산출물 처리 수정
- CLI 엔트리포인트 복구
- 전역 segment ID 보장
- 재귀 ingestion 지원

### Priority 1

- section draft/query/meta 저장 계약 복구
- `draft --section` happy path 보장
- 상태/액션 요약 신뢰도 복구

### Priority 2

- handoff summary 개선
- 사용자 문서/quickstart 개선
- lightweight review surface 추가 검토

## 8. 컨설턴트 관점의 성공 기준

업데이트 완료 후, 섹션 담당 컨설턴트는 아래를 할 수 있어야 한다.

1. 더미 자료가 들어온 workspace에서 자신의 섹션을 지정해 초안을 만든다.
2. 초안 안의 숫자/문장 중 무엇이 근거 충분한지와 무엇이 미확정인지 바로 구분한다.
3. 고객사 또는 내부 PM에게 요청해야 할 추가 자료 목록을 open query 형태로 바로 전달한다.
4. 재실행 후 어떤 부분이 개선되었는지 상태 파일과 섹션 패키지에서 확인한다.
5. 리드 승인 전까지 무엇이 막고 있는지 JSON 원문을 뒤지지 않고 이해한다.

## 9. 이번 계획에서 의도적으로 미루는 것

- 브라우저 기반 정식 웹앱
- 완성형 문서 편집기
- 최종 템플릿 이관 자동화의 고도화
- 외부 협업 시스템 연동

이 항목들은 파일 기반 PoC와 컨설턴트 workflow가 안정화된 뒤 후속 단계로 진행한다.

## 10. 권장 다음 액션

바로 다음 구현 배치에서는 아래 순서로 진행한다.

1. WS-1 Priority 0 작업 일괄 처리
2. 샘플 workspace로 P1-P3 smoke test 고정
3. WS-2에서 `draft --section`과 draft query loop 구현
4. WS-3에서 상태/액션 summary를 canonical source로 정리

