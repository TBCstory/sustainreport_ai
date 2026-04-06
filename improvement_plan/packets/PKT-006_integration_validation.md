# PKT-006: 통합 검증 및 문서화

## 목표
PKT-001~005에서 수행한 모든 수정이 일관성 있게 연결되는지 검증하고,
새 프로세스를 따르는 "빠른 시작 가이드"를 생성한다.

## 입력 파일
- PKT-001~005에서 생성/수정된 모든 파일
- `/Users/lj_homemac/tools/sustainreport_ai/CLAUDE.md`

## 출력 파일
1. **신규**: `improvement_plan/VALIDATION_REPORT.md` — 검증 결과
2. **신규**: `improvement_plan/QUICK_START_GUIDE.md` — 새 프로세스 빠른 시작 가이드

---

## 상세 작업

### STEP 1: 파일 존재 체크리스트

다음 파일이 모두 존재하는지 확인한다:

```
[ ] agents/intake-interviewer.md
[ ] agents/intake-interviewer.md (새 파일, .bak 아님)
[ ] agents/data-analyst.md.bak
[ ] agents/data-analyst.md (0단계, 5단계 포함)
[ ] agents/toc-planner.md.bak
[ ] agents/toc-planner.md (0단계~3단계 포함)
[ ] agents/section-writer.md.bak
[ ] agents/section-writer.md (0단계 포함)
[ ] schemas/intake_manifest.schema.json
[ ] schemas/data_gap_report.schema.json
[ ] orchestration/phase_rules.json (P0.5, P1.5 포함)
[ ] orchestration/gate_rules.json (GATE-P05-TO-P1, GATE-P15-TO-P2 포함)
```

각 파일에 대해 존재 여부와 핵심 키워드 포함 여부를 확인한다.

### STEP 2: 일관성 검증

다음 연결이 모두 성립하는지 확인한다:

| 연결 | 확인 내용 |
|------|-----------|
| intake-interviewer → toc-planner | toc-planner가 intake_manifest.json을 필수 입력으로 참조하는가 |
| intake-interviewer → section-writer | section-writer가 intake_manifest의 스타일을 적용하는가 |
| data-analyst → section-writer | section-writer가 data_gap_report를 참조하는가 |
| toc-planner → phase_rules | P1.5 페이즈가 toc-planner를 agent로 지정하는가 |
| phase_rules → gate_rules | P1.5 exit gate가 GATE-P15-TO-P2인가 |
| CLAUDE.md → agents 테이블 | intake-interviewer가 서브에이전트 일람에 있는가 |

### STEP 3: 레트로스펙티브 적용 — PRJ-2026-KRS-001 기준

이번 개선이 PRJ-2026-KRS-001에서 발생한 갭을 어떻게 해소하는지 확인한다:

| 갭 항목 | 개선 조치 | 해소 여부 |
|---------|----------|-----------|
| 목차 방식 사전 확정 없음 | intake-interviewer A-1 질문 | ✅/❌ |
| 정보보안 섹션 누락 | intake-interviewer A-2 포함/제외 확인 | ✅/❌ |
| 서술 스타일 미확정 | intake-interviewer B-1 질문 | ✅/❌ |
| HWP 처리 한계 미고지 | data-analyst 0단계 고지 | ✅/❌ |
| 데이터 갭 시각화 없음 | data-analyst 5단계 갭 리포트 | ✅/❌ |
| 활동 사례 부재 무언급 | section-writer 0-2 경고 | ✅/❌ |
| 목차 승인 단계 없음 | toc-planner 2단계 + P1.5 게이트 | ✅/❌ |

각 항목에 대해 실제 파일 내용을 확인하여 ✅ 또는 ❌를 기입한다.

### STEP 4: QUICK_START_GUIDE.md 생성

새 프로세스를 컨설턴트가 한눈에 볼 수 있는 가이드를 작성한다:

```markdown
# sustainreport_ai 빠른 시작 가이드 (개선 후)

## 새 프로세스 흐름 요약

```
1. P0: 프로젝트 기본 정보 입력 (기관명, 기간, 프레임워크)
   → project_charter.json 생성

2. P0.5: 인테이크 인터뷰 [신규]
   → AI가 8~10개 질문을 통해 아래를 확정합니다:
     ✓ 보고서 목차 방식 (프레임워크 기준 / 테마 기준 / 기존 목차 참조)
     ✓ 포함/제외 섹션 (정보보안 포함? 협력사 제외? 등)
     ✓ 서술 스타일 (체계 설명 위주 / 활동 성과 위주)
     ✓ 문체, 회사명 규칙
     ✓ 레퍼런스 보고서 여부
   → intake_manifest.json 저장

3. P1: 자료 투입
   → 파일 변환 시작
   → ⚠️ HWP 파일이 있으면 즉시 고지: "이 파일은 자동 변환이 안 됩니다.
      어떻게 처리하시겠습니까?" (영향 섹션 함께 표시)
   → 📊 데이터 갭 리포트 자동 생성: 섹션별 데이터 충족도 가시화

4. P1.5: 목차 논의 [신규]
   → intake_manifest 기반 목차 초안 생성
   → 컨설턴트 검토 및 수정 → 승인
   → ✅ 승인된 목차 확정

5. P2: 블루프린트 생성
   → 승인된 목차 기반으로 섹션별 작성 계약 생성
   → 컨설턴트 최종 승인 (P2→P3 게이트)

6. P3~P7: 기존과 동일
   → 단, section-writer가 활동 자료 부재 시 사전 경고 후 방향 결정 요청
```

## 컨설턴트가 준비하면 좋은 것들 (선택사항)

| 자료 | 용도 | 없어도 되는가 |
|------|------|-------------|
| 이전 연도 보고서 | 레퍼런스·스타일 참조 | 없어도 됨 |
| 이중중대성 평가 결과 | 섹션 깊이 배분 | 없어도 됨 |
| 인사팀 임직원 데이터 | SEC-2.1~2.2 수치 | 나중에 기재 가능 |
| 안전관리팀 재해율 데이터 | SEC-3.2 수치 | 나중에 기재 가능 |
| 2024년 활동 보고서 | 사례 중심 서술 | 없으면 체계 중심으로 전환 |

## 데이터가 없을 때 처리 방식

- 정량 수치 없음 → `[추후 기재: 담당팀 데이터 입수 후 기재]`
- 활동 사례 자료 없음 → 컨설턴트 확인 후 체계 설명 위주로 전환
- HWP 변환 불가 → 즉시 고지, 수동 변환 or [추후 기재] 선택
```

### STEP 5: IMPLEMENTATION_SPEC.json 최종 업데이트

모든 패킷이 완료됐으므로 IMPLEMENTATION_SPEC.json을 최종 업데이트한다:
- PKT-006의 status를 "done"으로 변경
- `"plan_status": "completed"` 필드 추가
- `"completed_at": <ISO8601>` 추가

---

## 완료 기준

1. `improvement_plan/VALIDATION_REPORT.md` 생성됨
2. 레트로스펙티브 표의 모든 항목이 ✅
   - ❌ 항목이 있으면 해당 패킷을 담당 에이전트에게 재작업 요청
3. `improvement_plan/QUICK_START_GUIDE.md` 생성됨
4. `IMPLEMENTATION_SPEC.json` 의 모든 패킷 status가 "done"

---

## 결정 원칙

- 검증 중 ❌ 발견 시: 즉시 실행을 멈추고 오케스트레이터에게 보고
  - "PKT-NNN 의 {항목}이 완료되지 않았습니다. PKT-NNN을 재실행해야 합니다."
- QUICK_START_GUIDE.md는 한국어로 작성하며, 기술 용어보다 컨설턴트 시각에서 읽기 쉽게 작성한다
- 검증 결과가 모두 ✅일 때만 PKT-006을 done 처리한다
