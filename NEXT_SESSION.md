# Session #20 — 실제 자료 투입 및 파이프라인 최적화

**생성일:** Session #19 완료 시  
**선행:** Session #19 전수 검증 완료 (8/8 테스트 통과)  
**상태:** 🟢 실행 준비 완료

---

## 목적

Session #20는 실제 PDF/DOCX 파일을 투입하여 **실전 환경 ingestion 파이프라인**을 검증합니다.
Session #13-19에서 구현한 모든 기능이 실제 자료에서도 정상 동작하는지 확인합니다.

---

## 현재 프로젝트 상태 (PRJ-2026-TST-003)

### Phase별 산출물 현황

| Phase | 산출물 | 상태 |
|-------|--------|------|
| P0 | project_charter.json, stakeholder_matrix.json | ✅ 완료 |
| P1 | file_registry.json, segment_manifest.json, SEG-00001.md | ✅ 완료 |
| P2 | structure_index.json, section_manifest.json, writing_blueprint.json | ✅ 완료 |
| P3 | framework_index.json, SEC-*.json 버킷 8개 | ✅ 완료 |
| P4 | SEC-*.md 초안 12개, SEC-*_meta.json 12개 | ✅ 완료 |
| P5 | internal_review_report.json, fact_check_report.json | ✅ 완료 |
| P6 | draft_package.json | ✅ 완료 |
| P7 | evidence_chain.json | ✅ 완료 |

### Session #19 검증 결과: 8/8 테스트 통과

| 테스트 | 결과 |
|--------|------|
| TC-1: 게이트 전수 검증 | ✅ 7/7 통과 |
| TC-2: 단위 테스트 | ✅ 12/12 통과 |
| TC-3: Disclosure ID 검증 | ✅ 5/5 통과 |
| TC-4: JSON 유효성 검증 | ✅ 43/43 통과 |
| TC-5: LLM API 호출 테스트 | ✅ 정상 응답 |
| TC-6: all_sections_drafted 조건 | ✅ 통과 |
| TC-7: SEC-3.1 provenance/anchor/placeholder | ✅ 존재 |
| TC-8: approval_gates.json 연동 | ✅ 반영됨 |

---

## Session #20 과제

### Phase 1: 실제 자료 투입 테스트

#### ST-1: 샘플 PDF/DOCX 파일 ingestion

실제 ESG 보고서 파일을 투입하여 ingestion 파이프라인을 테스트합니다.

```bash
# 1단계: 파일 메타데이터 확인
/opt/homebrew/bin/uv run python scripts/ingest_file.py \
  --workspace workspaces/PRJ-2026-TST-003 \
  --file /path/to/sample_esg_report.pdf \
  --file-type pdf

# 2단계: 텍스트 추출
/opt/homebrew/bin/uv run python -c "
from llm.file_processor import FileProcessor
processor = FileProcessor()
result = processor.extract_text('/path/to/sample_esg_report.pdf')
print(f'Extracted: {len(result[\"text\"])} chars')
print(f'Pages: {result.get(\"page_count\", \"N/A\")}')
"

# 3단계: 세그먼트 추출 및 정규화
/opt/homebrew/bin/uv run python scripts/extract_segments.py \
  --workspace workspaces/PRJ-2026-TST-003 \
  --file-id F-NEW-001 \
  --text "$( extracted_text )"
```

**기대 결과:**
- PDF/DOCX에서 텍스트 정상 추출
- 세그먼트 SEG-NNNNN 형식으로编号
- 03_normalized_md/에 정규화 파일 생성

#### ST-2: 텍스트 정규화 검증

```bash
# 정규화 출력 확인
cat workspaces/PRJ-2026-TST-003/03_normalized_md/F-NEW-001.md | head -30

# 세그먼트 추출 결과 확인
cat workspaces/PRJ-2026-TST-003/04_segments/SEG-NEW-00001.md 2>/dev/null || echo "SEG 파일 미생성"
```

**기대 결과:**
- 마크다운 형식으로 정규화
- heading hierarchy 유지
- 문단 단위 세그먼트 분리

### Phase 2: 파이프라인 최적화

#### ST-3: section-writer 에이전트 자동화 검증

현재 section-writer가 수동 실행인지 자동화 가능한지 확인합니다.

```bash
# section-writer 실행 스크립트 확인
ls -la scripts/section_writer*.py 2>/dev/null || echo "스크립트 없음"

# section-writer 에이전트 프롬프트 확인
cat agents/section-writer.md | head -50
```

**기대 결과:** section-writer 실행 방법 문서화 (자동화 가능 여부 판단)

#### ST-4: evidence 라우팅 검증

```bash
# 버킷 라우팅 로직 확인
cat scripts/route_to_buckets.py 2>/dev/null | head -30 || echo "라우팅 스크립트 없음"

# 기존 버킷 매핑 확인
ls workspaces/PRJ-2026-TST-003/06_buckets/
```

**기대 결과:** evidence → 버킷 라우팅 수동/자동 상태 확인

### Phase 3: 발견된 이슈 정리

```bash
# 발견된 이슈 기록
/opt/homebrew/bin/uv run python scripts/log_event.py \
  --type incident --agent orchestrator --phase P1 \
  --message "ST-1: 실제 파일 ingestion 테스트 결과" \
  --data '{"test": "ST-1", "file_type": "pdf", "status": "pending"}'
```

---

## Session #20 성공 기준

| 과제 | 기준 |
|------|------|
| ST-1 | 실제 PDF/DOCX 파일 ingestion 성공 |
| ST-2 | 텍스트 정규화 출력 정상 |
| ST-3 | section-writer 실행 방법 파악 |
| ST-4 | evidence 라우팅 방식 파악 |
| 이슈 기록 | blocking_issues.json 업데이트 |

---

## 발견된 버그 및 수정 이력 (Session #13-19)

### 수정 완료

| 버그 ID | 설명 | 수정 세션 |
|---------|------|----------|
| BUG-001 | check_gate.py: approval_gates.json 미확인 | Session #15 |
| BUG-002 | P2→P3 게이트 항상 needs_human_approval | Session #15 |
| BUG-003 | P5→P6 게이트 override 불가 | Session #15 |
| BUG-004 | all_sections_drafted 조건 미구현 | Session #17 |
| BUG-005 | LLM call_log agent 필드 미적용 | Session #17 |
| BUG-006 | edit_file 도구 경로 헤더 버그 | 우회 (터미널 파일 생성 사용) |

---

## Session #21 권장 과제

Session #20 완료 후 권장 작업:

1. **section-writer 에이전트 자동화**: 수동 → 자동화 스크립트 구현
2. **evidence 라우팅 자동화**: 버킷 자동 배정 로직 구현
3. **다중 파일 일괄 처리**: 배치 ingestion 스크립트 개발
4. **프레임워크별 disclosure 추출 자동화**: GRI/TCFD/KSSB/ESRS/SASB 매핑 자동화

---

## 출력물

Session #20 종료 시 다음을 업데이트해야 합니다:

1. `NEXT_SESSION.md` — Session #21 지시문
2. 실제 파일 ingestion 결과 `SESSION_LOG.md`에 기록
3. 발견된 이슈 `blocking_issues.json` 업데이트

```bash
# 테스트 결과 요약
/opt/homebrew/bin/uv run python scripts/log_event.py \
  --type progress --agent orchestrator --phase P1 \
  --message "Session #20 실제 자료 투입 테스트 완료"
```
