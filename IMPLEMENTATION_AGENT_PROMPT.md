# Implementation Agent Prompt

아래 프롬프트를 새 코딩 에이전트 세션의 첫 메시지로 사용한다.

---

```text
sustainreport_ai remediation 세션을 시작합니다.

이번 세션의 목적은 새 기능 탐색이 아니라, 2026-04-04 런타임 검증에서 재현된 실패를
`IMPLEMENTATION_EXECUTION_DIRECTIVES.md`에 따라 packet 단위로 복구하는 것입니다.

중요:
- 이전 `WP-1~7 DONE` 표기를 그대로 신뢰하지 마세요.
- 현재 authoritative 상태는 `IMPLEMENTATION_EXECUTION_DIRECTIVES.md`와 `IMPLEMENTATION_PROGRESS.md`입니다.

## 1. 반드시 읽을 파일

아래 파일만 먼저 읽으세요. 아직 다른 파일은 읽지 마세요.

1. `AGENTS.md`
2. `CLAUDE.md`
3. `GAP_REMEDIATION_UPDATE_PLAN.md`
4. `IMPLEMENTATION_EXECUTION_DIRECTIVES.md`
5. `IMPLEMENTATION_PROGRESS.md`

`purrfect-riding-blossom.md` 전체는 이 단계에서 읽지 마세요.
원 설계 의도 확인이 꼭 필요할 때만 필요한 섹션만 부분 참조하세요.

## 2. 작업 규칙

- 한 세션에 **한 remediation packet만** 수행하세요.
- `IMPLEMENTATION_PROGRESS.md`에서 아직 `DONE`이 아닌 가장 앞 packet 하나만 선택하세요.
- 선택한 packet의 `필수 읽기 파일`만 추가로 읽으세요.
- packet에 없는 범위로 확장하지 마세요.
- broad refactor, 웹 UI 추가, 새 의존성 추가를 하지 마세요.
- 변경은 packet의 완료 기준을 충족하는 최소 범위로 제한하세요.
- live command가 실패하면 먼저 deterministic regression test로 bug를 고정하고, packet 범위를 넘는 수정은 하지 마세요.

## 3. 세션 시작 출력 형식

파일들을 읽은 뒤, 아래 형식으로만 먼저 보고하세요.

1. 이번 세션에서 수행할 packet 이름
2. 읽을 추가 파일 목록
3. 수정 예정 파일 목록
4. 이 packet에서 하지 않을 것 3개 이하
5. 완료 기준

이 단계에서는 아직 코드를 수정하지 마세요.

## 4. 구현 후 필수 작업

구현이 끝나면 반드시 아래를 수행하세요.

- packet에 명시된 검증 명령 실행
- `IMPLEMENTATION_PROGRESS.md` 상태 업데이트
- `SESSION_LOG.md`에 이번 세션 handoff 기록

## 5. 주의

목표는 "계획된 시스템을 실제로 작동하게 복구하는 것"입니다.
추상화 추가나 아키텍처 미화보다, packet acceptance criteria 충족이 우선입니다.

가장 먼저 시작할 packet은 `WP-R1. Approval Canonicalization`입니다.
```
