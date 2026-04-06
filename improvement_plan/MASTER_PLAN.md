# sustainreport_ai 시스템 개선 마스터 플랜

## 개요

**배경**: PRJ-2026-KRS-001 (한국도로공사서비스 ESG S파트) 레트로스펙티브에서 식별된
주요 갭을 해소하기 위한 시스템 개선 계획.

**핵심 문제**: 컨설턴트와 사전 소통이 부족해 시스템이 모호한 가정 하에 작업을 진행했고,
이로 인해 목차 구조, 서술 스타일, 포함 범위 등 핵심 의사결정이 작업 도중 또는 사후에 조정됐다.

**개선 방향**: "묻고 확인하는" 단계를 파이프라인 앞에 배치하여,
컨설턴트가 충분한 정보를 가지고 지시할 수 있도록 한다.

---

## 전체 패킷 구성

```
PKT-001  인테이크 인터뷰어 에이전트 신설
   ↓
PKT-002  data-analyst 갭 리포트 + 파일 한계 고지 강화
   ↓
PKT-003  toc-planner 목차 논의 단계 추가
   ↓
PKT-004  section-writer 사례 부재 경고 + 자료 유형 구분 처리
   ↓
PKT-005  오케스트레이터 흐름 및 phase_rules 업데이트
   ↓
PKT-006  통합 검증 및 문서화
```

의존 관계:
- PKT-001, PKT-002는 독립적으로 시작 가능
- PKT-003은 PKT-001 완료 후
- PKT-004는 PKT-002 완료 후
- PKT-005는 PKT-001~004 모두 완료 후
- PKT-006은 PKT-005 완료 후

---

## 개선 전/후 파이프라인 비교

### Before (현재)
```
P0 프로젝트 정의
 └─ 컨설턴트: "KSSB 프레임워크로 S파트 써줘" (1문장)
P1 자료 투입
 └─ HWP 파일 발견 → 조용히 실패, 나중에 공백으로 나타남
P2 기획 (writing_blueprint)
 └─ 오케스트레이터 임의로 목차 설계
P3~P4 초안 작성
 └─ 활동 사례 없어도 경고 없이 체계 설명으로 작성
P5 검수 → P6 핸드오프
 └─ 이때야 컨설턴트가 "이게 내가 원하던 구조가 아닌데?" 발견
```

### After (개선 후)
```
P0 프로젝트 정의
P0.5 인테이크 인터뷰 [신규]
 └─ AI: "목차 방식은 어떻게? 정보보안 포함? 활동 중심 서술?"
 └─ 컨설턴트: 8~10개 질문에 답변 → intake_manifest.json 저장
P1 자료 투입
 └─ HWP 발견 즉시: "이 파일 변환 불가 → SEC-3.2 재해율 누락 가능 → 어떻게?"
 └─ 투입 완료 후 데이터 갭 리포트 자동 생성
P1.5 목차 논의 [신규]
 └─ toc-planner: intake_manifest 기반 목차 초안 제시
 └─ 컨설턴트 승인 또는 수정 → 확정
P2 writing_blueprint (승인된 목차 기반)
P3~P4 초안 작성
 └─ 활동 사례 없으면: "이 섹션 체계 중심으로 전환할까요? 아님 자료 추가 투입?"
P5~P7: 기존과 동일
```

---

## 각 패킷 요약

| 패킷 | 주요 변경 파일 | 핵심 산출물 |
|------|-------------|------------|
| PKT-001 | agents/intake-interviewer.md (신규) | intake_manifest.json 생성 에이전트 |
| PKT-002 | agents/data-analyst.md (수정) | data_gap_report.json, 파일 한계 고지 |
| PKT-003 | agents/toc-planner.md (수정) | toc_draft.json, 목차 승인 단계 |
| PKT-004 | agents/section-writer.md (수정) | 사례 부재 경고, 자료 유형별 서술 |
| PKT-005 | phase_rules.json, gate_rules.json, CLAUDE.md | P0.5/P1.5 페이즈, 게이트 |
| PKT-006 | VALIDATION_REPORT.md, QUICK_START_GUIDE.md | 검증 완료, 빠른 시작 가이드 |

---

## 매 세션 시작 방법

**모든 세션에서 동일한 지시문:**

```
/Users/lj_homemac/tools/sustainreport_ai/improvement_plan/SESSION_START_PROMPT.md
를 읽고, IMPLEMENTATION_SPEC.json에서 다음 미완료 패킷을 찾아 실행하세요.
```

진행 상태는 `IMPLEMENTATION_SPEC.json` 의 각 패킷 `status` 필드로 추적된다:
- `"pending"` → 미시작
- `"in_progress"` → 현재 세션에서 작업 중
- `"done"` → 완료

---

## 핵심 원칙 (변경 금지)

1. **컨설턴트 소통 우선**: 시스템이 가정해서 진행하는 것보다 질문하는 것이 낫다
2. **파일 처리 한계 즉시 고지**: 조용한 실패는 가장 나쁜 결과를 낳는다
3. **정량 데이터 공백은 괜찮다**: [추후 기재]로 유지하되 공백의 범위를 가시화한다
4. **기존 계약 하위 호환 유지**: 기존 agent 입출력 계약을 깨지 않는다
5. **백업 후 수정**: 기존 agent 파일 수정 시 반드시 .bak 파일 생성
