# PKT-002附属: 데이터 갭 리포트 생성 스크립트 명세

## 목적

`agents/data-analyst.md`의 5단계(데이터 갭 리포트 생성)를 자동화하는 Python 스크립트의 구현 명세를 제공한다.

**참고**: 실제 스크립트 구현은 PKT-005(오케스트레이터 흐름 업데이트)에서 처리한다. 이 문서는 구현时才 참조할 설계 문서이다.

---

## 스크립트基本信息

| 항목 | 값 |
|------|-----|
| 스크립트 경로 | `scripts/generate_data_gap_report.py` |
| Python 최소 버전 | 3.13 |
| 실행 시점 | P1 파일 변환 완료 후 (data-analyst 에이전트 5단계) |
| 입력 | `05_planning/structure_index.json`, `06_buckets/SEC-*.json`, `04_segments/` |
| 출력 | `02_file_registry/data_gap_report.json` |

---

## 기능 요구사항

### FR-1: 섹션 목록 수집

1. `05_planning/structure_index.json`이 존재하면 해당 파일에서 `sections` 배열을 읽는다
2. 각 섹션의 `section_id`, `section_title`, `notes`, `framework_mappings`를 추출한다
3. `structure_index.json`이 없으면 빈 보고서를 생성하고 사용자에게 `structure_index.json` 생성 필요를 알린다

### FR-2: 세그먼트 매핑

1. `06_buckets/` 디렉토리에서 `SEC-{id}.json` 파일들을 읽는다
2. 각 버킷 파일의 `assigned_segments` 목록을 통해 해당 섹션에 연결된 세그먼트를 추적한다
3. 버킷이 없는 섹션은 `04_segments/` 디렉토리에서 섹션 `notes` 키워드 기반 파일명 검색을 시도한다

### FR-3: 데이터 충족도 평가

각 섹션에 대해 다음 기준 적용:

| 점수 | 조건 |
|------|------|
| 1.0 (high) | 버킷 존재 + 세그먼트 3개 이상 + 정량 데이터 관련 세그먼트 포함 |
| 0.5 (medium) | 버킷 존재 + 세그먼트 1개 이상 + 정량 데이터 관련 세그먼트 포함 |
| 0.2 (low) | 버킷 존재하지만 정량 데이터 관련 세그먼트 없음 |
| 0.0 (none) | 버킷 없음 |

**정량 데이터 관련 세그먼트 판정 기준:**
- 세그먼트 파일명 또는 `heading_path`에 다음 키워드 포함: "수치", "통계", "비율", "건수", "명수", "LTIR", "TRIR", "재해율", "교육이수", "여성관리자", "채용", "离职"
- GRI 401/403/404/405/406 관련 section_id

### FR-4: 결측 데이터 유형 추정

1. 섹션의 `framework_mappings`를 확인
2. GRI 기준 매핑이 있는 섹션은 해당 GRI 지표의 필수 공개 항목을 결측 데이터로 등록
3. `notes`에 "수치", "통계" 키워드가 있는 섹션은 다음 유형 중 하나 이상을 결측으로 표시:
   - "3개년 추이 데이터"
   - "정량적 수치 (비율/건수)"
   - "담당 부서 데이터"

### FR-5: JSON 보고서 생성

`02_file_registry/data_gap_report.json`을 생성한다.

스키마: `schemas/data_gap_report.schema.json` 참조

### FR-6: 요약 보고 출력

콘솔에 다음 형식 출력:

```
📊 데이터 갭 리포트

전체 {N}개 섹션 중:
- 🟢 데이터 충족 ({N}개): {쉼표分隔 섹션 ID 목록}
- 🟡 부분 확보 ({N}개): {쉼표分隔 섹션 ID 목록}
- 🔴 데이터 부족 ({N}개): {쉼표分隔 섹션 ID 목록}

⚠️ 즉시 확보 권장 데이터:
1. {데이터명} → 추정 원인 → 영향 섹션: {SEC-X}
2. ...

전체 상세 내용: 02_file_registry/data_gap_report.json
```

---

## 명령줄 인터페이스

```bash
python scripts/generate_data_gap_report.py \
  --workspace /path/to/PRJ-YYYY-CODE-NNN \
  [--structure-index 05_planning/structure_index.json] \
  [--buckets-dir 06_buckets/] \
  [--segments-dir 04_segments/] \
  [--output 02_file_registry/data_gap_report.json]
```

| 인자 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `--workspace` | 예 | - | 프로젝트 워크스페이스 경로 |
| `--structure-index` | 아니오 | `{workspace}/05_planning/structure_index.json` | 섹션 구조 인덱스 파일 |
| `--buckets-dir` | 아니오 | `{workspace}/06_buckets/` | 버킷 디렉토리 |
| `--segments-dir` | 아니오 | `{workspace}/04_segments/` | 세그먼트 디렉토리 |
| `--output` | 아니오 | `{workspace}/02_file_registry/data_gap_report.json` | 출력 파일 경로 |

---

## 오류 처리

| 상황 | 처리 |
|------|------|
| `structure_index.json` 없음 | 경고 출력 후 빈 `sections: []`로 보고서 생성. exit code 0 |
| `06_buckets/` 디렉토리 없음 | 경고 출력 후 모든 섹션을 `data_readiness: low` 처리 |
| `04_segments/` 디렉토리 없음 | `available_segments: []`로 처리 |
| 출력 디렉토리 없음 | 디렉토리를 먼저 생성 |
| JSON 쓰기 실패 | 오류 메시지 출력 후 exit code 1 |

---

## 의존성

- Python 표준 라이브러리만 사용 (os, json, argparse, pathlib)
- 외부 의존성 없음

---

## 구현时才 참고

이 명세는 PKT-005(오케스트레이터 흐름 업데이트)에서 실제 스크립트로 구현된다. 구현 시:

1. `agents/data-analyst.md`의 5단계 설명과 이 명세의 불일치 발생 시 **이 문서**가 정답이다
2. 스크립트 실행 결과를 `context_bus/events.jsonl`에 기록해야 한다
3. `--dry-run` 옵션으로 실제 파일 생성 없이 출력 확인이 가능해야 한다