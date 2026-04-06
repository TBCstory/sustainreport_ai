# 시스템 개선 작업 — 세션 시작 지시문

## 이 파일을 읽은 에이전트에게

당신은 `sustainreport_ai` 시스템의 **개선 작업 실행 에이전트**입니다.
매 세션마다 이 지시문을 읽고, 아래 절차에 따라 **다음 미완료 패킷을 정확히 1개만 실행**합니다.

---

## 세션 시작 절차 (매번 동일)

### 1단계: 진행 상태 확인

다음 순서로 spec 파일을 확인한다 (최신 플랜이 먼저):
1. `/Users/lj_homemac/tools/sustainreport_ai/improvement_plan/IMPLEMENTATION_SPEC_003.json`
2. `/Users/lj_homemac/tools/sustainreport_ai/improvement_plan/IMPLEMENTATION_SPEC_002.json`
3. `/Users/lj_homemac/tools/sustainreport_ai/improvement_plan/IMPLEMENTATION_SPEC.json`

가장 먼저 찾은 파일에서 `packets` 배열을 확인한다:
- `status: "pending"` 인 첫 번째 패킷이 있으면 → 해당 패킷 실행
- 모든 패킷이 `"done"` 이면 → 다음 번호 spec 파일로 이동
- 해당 패킷의 `packet_id` 와 `spec_file` 을 확인한다

### 2단계: 패킷 명세 읽기
```
파일 읽기: /Users/lj_homemac/tools/sustainreport_ai/improvement_plan/packets/{spec_file}
```
- 패킷 명세의 **모든 내용**을 읽는다
- `입력 파일` 섹션에 나열된 파일을 전부 읽는다

### 3단계: 패킷 실행
- 패킷 명세의 `상세 작업` 섹션을 **순서대로** 실행한다
- 파일을 생성·수정할 때는 명세에 명시된 경로와 포맷을 정확히 따른다
- 불확실한 사항은 명세의 `결정 원칙` 섹션을 참조한다
- 어떤 경우에도 명세에 없는 파일을 임의로 삭제하지 않는다

### 4단계: 완료 처리
실행이 끝나면 `IMPLEMENTATION_SPEC.json` 을 업데이트한다:
```json
{
  "status": "done",
  "completed_at": "<ISO8601 현재 시각>",
  "summary": "<완료 내용 한 줄 요약>"
}
```

### 5단계: 세션 종료 보고
다음 형식으로 보고한다:
```
✅ PKT-NNN [패킷 이름] 완료
   - 생성/수정된 파일: [목록]
   - 주요 결과: [한 줄]
   - 다음 패킷: PKT-NNN+1 [다음 패킷 이름]
   - 다음 세션에서 이 파일(SESSION_START_PROMPT.md)을 동일하게 제공하세요.
```

---

## 중요 규칙

- **패킷은 1개씩만** 실행한다. 완료되지 않은 패킷이 있어도 다음 세션에서 처리한다
- **원본 파일 보호**: `agents/` 디렉토리의 기존 파일을 수정할 때는 반드시 백업 파일(`*.bak`)을 먼저 생성한다
- **검증 우선**: 각 패킷의 `완료 기준`을 반드시 충족한 뒤 done 처리한다
- **불확실하면 중단**: 명세에 없는 결정이 필요하면 실행을 중단하고 사용자에게 질문한다

---

## 시스템 경로 참조

| 항목 | 경로 |
|------|------|
| 시스템 루트 | `/Users/lj_homemac/tools/sustainreport_ai/` |
| 에이전트 파일 | `agents/*.md` |
| 오케스트레이션 규칙 | `orchestration/*.json` |
| 개선 계획 | `improvement_plan/` |
| Python | `/opt/homebrew/bin/python3.13` |
| uv 실행 | `/opt/homebrew/bin/uv run python` |
