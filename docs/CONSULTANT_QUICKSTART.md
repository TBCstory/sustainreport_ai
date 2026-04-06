docs/CONSULTANT_QUICKSTART.md
```

```markdown
# 컨설턴트 빠른 시작 가이드

이 가이드는 **섹션 담당 컨설턴트**가 자신의 섹션 초안을 작성하고, open query를 추적하며, 재검토가 필요한 섹션을 파악하는 과정을 설명합니다.

---

## 1. 내 섹션 초안 생성하기

### 1-1. 프로젝트 상태 확인

```bash
sustainreport status --workspace workspaces/PRJ-2026-TST-003
```

출력 예시:
```
=== PRJ-2026-TST-003 Status ===
  Current Phase  : P4
  Blocking Issues: 3 unresolved (0 blocker)
  Open Queries   : 5

  Next Actions (top 3):
    [ACT-001] (data_request) SEC-3.1 — 배출량 데이터 확인 필요
    [ACT-002] (evidence_gathering) SEC-3.2 — 거버넌스 체계 증거 필요
    ...
```

### 1-2. 특정 섹션 초안 생성

```bash
# 특정 섹션만
sustainreport run-draft --workspace workspaces/PRJ-2026-TST-003 --section SEC-3.1

# 여러 섹션
sustainreport run-draft --workspace workspaces/PRJ-2026-TST-003 --section SEC-3.1 --section SEC-3.2
```

생성 후 출력:
```
P4 Section Writer completed.
  Sections written: 2/2
  Outputs: ['07_drafts/SEC-3.1.md', '07_drafts/SEC-3.1_meta.json', ...]
```

### 1-3. 초안 결과 확인

생성된 파일:
- **초안 본문**: `07_drafts/SEC-3.1.md`
- **메타데이터**: `07_drafts/SEC-3.1_meta.json` (신뢰도, 플레이스홀더 수, 소스 태그 수 포함)

---

## 2. 초안 검토 포인트

`07_drafts/SEC-3.1_meta.json` 파일의 값을 확인하세요.

| 필드 | 의미 | 주의 필요 |
|------|------|----------|
| `draft_confidence` | 신뢰도 (0~1) | 0.8 이상이면 양호, 0.6 미만이면 증거 보강 필요 |
| `placeholder_count` | 플레이스홀더 개수 | 5개 이상이면 작업 필요 |
| `source_tag_count` | 출처 태그 개수 | 숫자가 낮으면 근거 부족 가능성 |

### 플레이스홀더란?

`[확인필요: ...]` 형식의 텍스트로, 아직 확인되지 않았거나 증거가 부족한 부분입니다.

예시:
```
[확인필요: 2024년 Scope 1 배출량 1,250 tCO2e — 출처: SEG-00001]
```

### 플레이스홀더를 Query로 등록하기

`run_draft` 실행 시 플레이스홀더가 자동으로 `draft_queries.json`에 등록됩니다.

---

## 3. Open Query 관리

### 3-1. Open Query 목록 확인

```bash
cat workspaces/PRJ-2026-TST-003/draft_queries.json
```

또는 `status` 명령으로 요약 확인:
```
Open Queries   : 5
```

### 3-2. Query 우선순위

| 우선순위 | 아이콘 | 의미 |
|----------|--------|------|
| critical | 🔴 | 즉시 확인 필요 (오류, 불일치) |
| high | 🟠 |尽快 확인 (데이터 요청) |
| medium | 🟡 | 차기 검토 시 확인 |
| low | 🟢 | 참고용 |

---

## 4. 핸드오프 요약 확인

P6 단계 완료 후 `09_handoff/handoff_summary.md` 파일이 생성됩니다.

이 파일에서 확인할 내용:
- **섹션별 신뢰도** — 어느 섹션이 승인 가능한 수준인지
- **플레이스홀더 수** — 증거 보강이 필요한 섹션
- **Open Query 목록** — 고객사/내부 PM에게 요청할 사항
- **재검토 권장 섹션** — 수정이 필요한 섹션 목록

---

## 5. 내 섹션 재실행

증거가 추가된 후 초안을 다시 생성하려면:

```bash
sustainreport run-draft --workspace workspaces/PRJ-2026-TST-003 --section SEC-3.1
```

이전 초안은 `07_drafts/SEC-3.1.md.bak`으로 백업됩니다.

---

## 6. 일반적인 작업 흐름

```
1. receive assignment  →  SEC-3.1 기후변화 대응 섹션 담당
2. status 확인         →  현재 상태 파악
3. run-draft --section SEC-3.1  →  초안 생성
4. meta.json 확인      →  신뢰도, 플레이스홀더 수 확인
5. draft_queries.json  →  open query 목록 확인
6. 증거 보강/고객 요청 →  필요한 자료 요청
7. 재실행              →  run-draft로 초안 갱신
8. handoff_summary.md  →  최종 검토 및 인계
```

---

## 7. 자주 묻는 질문

**Q: 플레이스홀더가 많습니다. 어떻게 해야 하나요?**
A: `draft_queries.json`의 open query 목록을 확인하고, 해당 자료를客户提供 또는 내부에서 확보하세요. 자료가 없으면 플레이스홀더를 남겨둔 채 인계하는 것도 옵션입니다.

**Q: 신뢰도가 0.5인데 게이트가 통과되나요?**
A: 신뢰도 낮음은 정상입니다. 컨설턴트가 검토 후 승인하면 `approved` 상태로 변경됩니다.

**Q: 내 섹션이 'needs_work'로 표시됩니다.**
A: 플레이스홀더가 5개 이상이라는 의미입니다. 증거를 보강하거나 query를 resolved 처리하세요.

---

## 8. 관련 파일 위치

| 파일 | 경로 | 용도 |
|------|------|------|
| 초안 | `07_drafts/SEC-X.Y.md` | 섹션 초안 본문 |
| 메타 | `07_drafts/SEC-X.Y_meta.json` | 신뢰도, 플레이스홀더 수 |
| Query | `draft_queries.json` | 미해결 질문 목록 |
| 요약 | `09_handoff/handoff_summary.md` | 프로젝트 전체 요약 (P6 이후) |
| 상태 | `project_state.json` | 현재 페이즈, 통계 |