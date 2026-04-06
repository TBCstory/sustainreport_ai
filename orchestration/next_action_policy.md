# Next Action Policy

## 목적

오케스트레이터가 `project_state.json`, `blocking_issues.json`, `next_actions.json`을 읽은 뒤
사용자에게 **지금 바로 해야 할 다음 행동 3개 이하**를 안정적으로 제안하기 위한 baseline 규칙이다.

## 입력 소스

- `project_state.json`
- `blocking_issues.json`
- `next_actions.json`
- `approval_gates.json`

## 제안 규칙

1. 항상 **최대 3개 이하**의 행동만 제안한다.
2. 이미 `next_actions.json`에 canonical action이 있으면 그 항목을 우선 사용하고, 중복 action을 새로 만들지 않는다.
3. 우선순위는 아래 순서를 따른다.
   - 현재 phase를 막는 human approval 또는 gate blocker
   - severity가 `blocker` 또는 `high`인 unresolved issue
   - open draft query 또는 missing evidence 보강 요청
   - 현재 phase에서 바로 재실행 가능한 deterministic command
4. 제안 문구는 사람이 바로 실행할 수 있게 작성한다.
   - 가능한 경우 정확한 명령 또는 확인 대상 파일을 적는다.
   - JSON 수동 편집을 유도하지 않는다.
5. 증거 부족 상황에서는 사실을 메우지 말고 placeholder 유지, query 등록, 추가 자료 요청을 우선 제안한다.

## 타이브레이커

- 현재 phase blocker가 historical cleanup보다 우선한다.
- human approval 대기가 optional 품질 개선보다 우선한다.
- 사용자 담당 section의 blocker가 전역 nice-to-have보다 우선한다.

## 비목표

- 4개 이상의 행동 나열
- 승인 게이트 우회 제안
- 원문 JSON 직접 수정 안내
