# sustainreport_ai Hardening Work Order

> **용도**: 이 문서는 다른 에이전트가 세션마다 동일한 지시문으로 순차 작업할 수 있는 **자기완결형 작업 지시서**이다.
> **작성일**: 2026-04-05
> **근거**: AUD-2 감사 findings (F1~F6) + 최초 설계 `purrfect-riding-blossom.md` 기준 gap 분석

---

## 사용 방법

**매 세션 시작 시 에이전트에게 아래 지시문을 동일하게 준다:**

```
@HARDENING_WORK_ORDER.md 를 읽고, 현재 미완료 상태인 가장 앞 packet부터 작업을 시작해.
packet 완료 시 이 문서의 해당 packet 상태를 DONE으로 업데이트하고, 검증 결과를 기록해.
```

에이전트는:
1. 이 문서를 읽는다
2. `## Packet Status` 테이블에서 첫 번째 `TODO` packet을 찾는다
3. 해당 packet의 지시를 따라 구현한다
4. 검증을 수행한다
5. 이 문서의 상태를 `DONE`으로 갱신하고 검증 결과를 기록한다
6. 시간이 남으면 다음 packet으로 진행한다

---

## Packet Status

| Packet | 이름 | 상태 | 의존성 | 완료일 | 검증 결과 |
|--------|------|------|--------|--------|-----------|
| HD-1 | Ingestion Idempotency | DONE | 없음 | 2025-01-15 | 3 passed |
| HD-2 | Segment Manifest + Bucket Grounding | DONE | HD-1 | 2025-01-15 | 3 passed |
| HD-3 | Writer Contract Enforcement | DONE | HD-2 | 2025-01-15 | 3 passed |
| HD-4 | Pipeline Status Sync | DONE | 없음 (독립) | 2025-01-15 | 2 passed |
| HD-5 | Draft Query Typed Fields | DONE | 없음 (독립) | 2025-01-15 | 4 passed |

**의존성 규칙**:
- HD-1 → HD-2 → HD-3은 반드시 순차 실행
- HD-4, HD-5는 어느 시점에서든 독립 실행 가능
- 한 세션에서 여러 packet 완료 가능 (시간이 허락하면)

---

## 공통 규칙

### 코드 수정 원칙
- 기존 함수 시그니처를 바꾸지 않는다 (하위 호환)
- 새 함수를 추가하고, 기존 흐름에 삽입한다
- 모든 수정은 기존 테스트(`pytest tests/ -q`)를 깨뜨리지 않아야 한다
- 새 기능에 대한 테스트를 추가한다

### 검증 절차 (매 packet 공통)
1. `python3.13 -m py_compile scripts/run_ingestion.py scripts/run_framework_mapper.py scripts/run_section_writer.py scripts/dispatch_agent.py scripts/run_pipeline.py scripts/rebuild_summaries.py llm/cli.py scripts/utils.py` — syntax OK
2. `.venv/bin/pytest tests/ -q` — 기존 테스트 전부 통과 + 새 테스트 통과
3. packet별 acceptance criteria 확인 (아래 각 packet에 명시)

### 파일 경로 규약
- 프로젝트 루트: `/Users/lj_homemac/tools/sustainreport_ai/`
- Python: `/opt/homebrew/bin/python3.13`
- venv: `.venv/bin/python`, `.venv/bin/pytest`
- 워크스페이스 위치: `workspaces/PRJ-*`

---

## HD-1: Ingestion Idempotency

### 문제 (AUD-2 Finding F1)
`run_ingestion.py`에 content hash 기반 중복 탐지가 없다. 같은 raw 파일을 다시 투입하면 새 F-ID와 SEG-ID가 무한히 생성된다.

### 설계 기준
`purrfect-riding-blossom.md` §1.5: 파일 상태머신에서 `received → registered` 전환 시 중복 체크가 전제되어 있다.

### 수정 대상
`scripts/run_ingestion.py`

### 현재 코드 구조
```
get_next_file_id(registry_path) → int              # line 72-88, max(existing) + 1
_load_next_segment_id(workspace) → int              # line 91-100
_save_next_segment_id(workspace, next_id)           # line 103-110
split_segments(content, source_file_id, ...) → list # line 167-250
run_ingestion(workspace, file_paths, state_manager) # line 258-484
```

- F-ID 할당: line 336 `file_id = f"F-{next_file_num:04d}"`
- SEG-ID 할당: line 222 `segment_id = f"SEG-{seg_num:05d}"`
- file_registry.json 쓰기: line 425-429
- segment_manifest.json 쓰기: line 460-469
- 현재 dedup 로직: **없음**

### 구현 지시

#### Step 1: content hash 함수 추가
`run_ingestion.py` 상단 (import 영역 뒤, line ~70 부근)에 추가:

```python
import hashlib

def _compute_content_hash(file_path: Path) -> str:
    """파일의 SHA-256 content hash를 계산한다."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"
```

#### Step 2: 기존 registry에서 hash lookup 함수 추가

```python
def _find_existing_file_by_hash(
    registry_data: dict, content_hash: str
) -> Optional[str]:
    """registry에서 동일 content_hash를 가진 기존 F-ID를 찾는다.
    없으면 None 반환."""
    for entry in registry_data.get("files", []):
        if entry.get("content_hash") == content_hash:
            return entry.get("file_id")
    return None
```

#### Step 3: run_ingestion() 메인 루프 수정
`run_ingestion()` 내 파일 처리 루프 (line ~316-420)에서, 각 파일 처리 시작 직후:

1. `_compute_content_hash(raw_path)` 호출
2. `_find_existing_file_by_hash(registry_data, content_hash)` 호출
3. 기존 F-ID가 있으면:
   - 해당 파일을 건너뛰고 `skipped_duplicates` 카운터 증가
   - `results["skipped_files"]` 리스트에 `{"path": str(raw_path), "existing_file_id": existing_fid, "reason": "content_hash_duplicate"}` 추가
   - **새 F-ID/SEG-ID 생성하지 않음**
4. 기존 F-ID가 없으면 기존 흐름 그대로 진행
5. file_registry 엔트리에 `"content_hash": content_hash` 필드 추가 (line ~340-380 부근, 엔트리 dict에)

#### Step 4: 반환값 업데이트
`run_ingestion()` 반환 dict에 `"skipped_files"` 키 추가 (기존 키: success, files_processed, files_success, files_failed, segments_created, outputs, errors)

### 테스트 추가

`tests/test_ingestion_idempotency.py` 신규 파일:

```python
"""HD-1: Ingestion idempotency — 같은 파일 2회 투입 시 F/SEG 중복 방지."""
import json
import tempfile
from pathlib import Path

def _make_workspace(tmp: Path) -> Path:
    """최소 워크스페이스 구조 생성."""
    ws = tmp / "PRJ-TEST-HD1"
    for d in ["00_definition", "01_raw", "02_file_registry",
              "03_normalized_md", "04_segments"]:
        (ws / d).mkdir(parents=True, exist_ok=True)
    # P0 정의 파일
    (ws / "00_definition" / "project_charter.json").write_text(
        json.dumps({"project_id": "PRJ-TEST-HD1"}), encoding="utf-8")
    (ws / "00_definition" / "stakeholder_matrix.json").write_text(
        json.dumps({"stakeholders": []}), encoding="utf-8")
    return ws

def test_same_file_twice_no_duplicate():
    """같은 파일을 2회 투입하면 두 번째는 skip되어야 한다."""
    from scripts.run_ingestion import run_ingestion
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        # 테스트 파일 생성
        test_file = ws / "01_raw" / "test_report.txt"
        test_file.write_text("# ESG Report\nSample content for testing.", encoding="utf-8")

        # 1회차 투입
        r1 = run_ingestion(ws, [str(test_file)])
        assert r1["success"] is True
        assert r1["files_success"] >= 1

        # registry 확인
        reg1 = json.loads((ws / "02_file_registry" / "file_registry.json").read_text())
        f_count_1 = len(reg1.get("files", []))

        # segment manifest 확인
        seg1 = json.loads((ws / "04_segments" / "segment_manifest.json").read_text())
        seg_count_1 = len(seg1.get("segments", []))

        # 2회차 투입 (같은 파일)
        r2 = run_ingestion(ws, [str(test_file)])
        assert r2["success"] is True
        assert len(r2.get("skipped_files", [])) >= 1

        # registry에 F-ID 중복 없음
        reg2 = json.loads((ws / "02_file_registry" / "file_registry.json").read_text())
        f_count_2 = len(reg2.get("files", []))
        assert f_count_2 == f_count_1, f"F-ID duplicated: {f_count_1} → {f_count_2}"

        # segment manifest에 SEG 중복 없음
        seg2 = json.loads((ws / "04_segments" / "segment_manifest.json").read_text())
        seg_count_2 = len(seg2.get("segments", []))
        assert seg_count_2 == seg_count_1, f"SEG duplicated: {seg_count_1} → {seg_count_2}"

def test_different_file_creates_new_ids():
    """다른 파일은 정상적으로 새 F-ID/SEG를 생성해야 한다."""
    from scripts.run_ingestion import run_ingestion
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        f1 = ws / "01_raw" / "report_a.txt"
        f1.write_text("# Report A\nContent A.", encoding="utf-8")
        f2 = ws / "01_raw" / "report_b.txt"
        f2.write_text("# Report B\nContent B.", encoding="utf-8")

        r1 = run_ingestion(ws, [str(f1)])
        r2 = run_ingestion(ws, [str(f2)])
        assert r1["success"] and r2["success"]
        assert len(r2.get("skipped_files", [])) == 0

        reg = json.loads((ws / "02_file_registry" / "file_registry.json").read_text())
        assert len(reg.get("files", [])) >= 2

def test_content_hash_stored_in_registry():
    """file_registry 엔트리에 content_hash 필드가 있어야 한다."""
    from scripts.run_ingestion import run_ingestion
    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))
        f = ws / "01_raw" / "test.txt"
        f.write_text("# Test\nHello.", encoding="utf-8")
        run_ingestion(ws, [str(f)])

        reg = json.loads((ws / "02_file_registry" / "file_registry.json").read_text())
        entry = reg["files"][0]
        assert "content_hash" in entry
        assert entry["content_hash"].startswith("sha256:")
```

### Acceptance Criteria
1. 같은 파일 2회 투입 → F-ID, SEG-ID 개수 불변
2. 다른 파일 투입 → 정상적으로 새 ID 생성
3. `file_registry.json`의 모든 엔트리에 `content_hash` 필드 존재
4. 반환값에 `skipped_files` 키 포함
5. 기존 테스트 전부 통과

---

## HD-2: Segment Manifest + Bucket Grounding 복구

### 문제 (AUD-2 Finding F2)
`segment_manifest.json`에 `file_path` 필드가 누락되어, `_find_segments_for_section()`이 세그먼트 본문을 읽지 못한다. 결과적으로 fresh lane에서 대부분의 bucket이 empty/fallback이다.

### 설계 기준
`purrfect-riding-blossom.md` §2.3: keyword + framework 매칭으로 세그먼트를 섹션에 라우팅하며, 충분한 자료가 있으면 ~60% 이상 grounded bucket이 기대된다.

### 수정 대상
1. `scripts/run_ingestion.py` — segment_manifest 엔트리 보강
2. `scripts/run_framework_mapper.py` — segment content 로드 + keyword matching 강화

### 현재 코드 구조

**run_ingestion.py segment_manifest 생성** (line 432-469):
- segments_dir의 모든 `SEG-*.md` 파일을 스캔
- 각 파일에서 YAML front matter 파싱 → manifest 엔트리 생성
- 현재 엔트리 필드: `segment_id`, `source_file_id`, `heading_path`, `created_at`
- **`file_path` 필드 없음**, **`content_preview` 필드 없음**

**run_framework_mapper.py _find_segments_for_section()** (line 122-227, nested in _build_buckets_from_structure_index):
- line 145-157: 세그먼트 파일에서 content 로드 시도
- heading_path와 toc_path의 키워드 매칭
- framework_mappings의 disclosure와 세그먼트 content 매칭

### 구현 지시

#### Part A: run_ingestion.py — segment_manifest 엔트리 보강

**Step 1**: segment_manifest 생성 루프 (line ~435-458)에서 각 엔트리에 2개 필드 추가:

```python
# 세그먼트 본문 경로 (정규화된 MD가 아닌 segment 파일 자체)
entry["file_path"] = str(seg_file.relative_to(workspace))

# content_preview: 본문 첫 500자 (front matter 제외)
content_body = _extract_body_from_segment(seg_file)
entry["content_preview"] = content_body[:500] if content_body else ""
```

**Step 2**: `_extract_body_from_segment(seg_path: Path) -> str` 헬퍼 추가:
```python
def _extract_body_from_segment(seg_path: Path) -> str:
    """세그먼트 파일에서 YAML front matter를 제외한 본문을 추출한다."""
    text = seg_path.read_text(encoding="utf-8")
    # --- front matter --- 패턴 제거
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3:].strip()
    return text.strip()
```

#### Part B: run_framework_mapper.py — segment content 로드 강화

**Step 1**: `_find_segments_for_section()` (line 122-227) 내 세그먼트 content 로드 부분 수정.

현재 로직을 아래 순서로 강화:
1. `manifest_entry.get("file_path")`가 있으면 해당 경로에서 읽기
2. 없으면 `04_segments/SEG-NNNNN.md` 직접 읽기 (기존 fallback)
3. 둘 다 실패하면 `content_preview` 필드 사용
4. 모두 실패하면 heading_path만으로 매칭 (현재 최소 동작)

```python
def _load_segment_content(workspace: Path, seg_entry: dict) -> str:
    """세그먼트 본문을 로드한다. 여러 경로를 순서대로 시도."""
    # 1) file_path 필드
    fp = seg_entry.get("file_path")
    if fp:
        full = workspace / fp
        if full.exists():
            return _extract_body(full)

    # 2) 직접 경로
    seg_id = seg_entry.get("segment_id", "")
    direct = workspace / "04_segments" / f"{seg_id}.md"
    if direct.exists():
        return _extract_body(direct)

    # 3) content_preview fallback
    preview = seg_entry.get("content_preview", "")
    if preview:
        return preview

    return ""
```

**Step 2**: keyword matching 로직 강화

`_find_segments_for_section()` 내에서 매칭 점수 계산 시, 기존 heading_path + toc_path 키워드에 더해:

1. blueprint의 `required_subsections` 키워드도 매칭 대상에 추가
2. blueprint의 `framework_disclosures` (예: "GRI 305-1")도 content에서 검색
3. 매칭 키워드가 2개 이상이면 confidence에 +0.1 보너스

```python
# blueprint에서 추가 키워드 추출
bp_keywords = []
if section_blueprint:
    bp_keywords.extend(section_blueprint.get("required_subsections", []))
    bp_keywords.extend(section_blueprint.get("framework_disclosures", []))

# content에서 키워드 매칭
match_count = 0
content_lower = content.lower()
for kw in all_keywords:  # heading keywords + bp_keywords
    if kw.lower() in content_lower:
        match_count += 1

# match_count 기반 confidence 조정
if match_count >= 3:
    confidence_bonus = 0.15
elif match_count >= 2:
    confidence_bonus = 0.1
else:
    confidence_bonus = 0.0
```

**Step 3**: bucket confidence 계산 수정

현재 문제: segments가 비어있어도 framework_mappings가 있으면 confidence=0.9가 될 수 있음 (EG-1B에서 일부 수정했으나 불완전).

수정:
```python
# 버킷 confidence 결정 (line ~238-248 부근)
if matched_segments:
    bucket_confidence = sum(s["confidence_score"] for s in matched_segments) / len(matched_segments)
    bucket_status_type = "grounded"
else:
    bucket_confidence = 0.0  # segments 없으면 무조건 0.0
    bucket_status_type = "empty"
```

### 테스트 추가

`tests/test_bucket_grounding.py` 신규:

```python
"""HD-2: Segment manifest file_path 보장 + bucket grounding 복구."""
import json
import tempfile
from pathlib import Path

def _make_workspace_with_segments(tmp: Path, num_files: int = 3) -> Path:
    """세그먼트가 있는 워크스페이스 생성."""
    ws = tmp / "PRJ-TEST-HD2"
    for d in ["00_definition", "01_raw", "02_file_registry",
              "03_normalized_md", "04_segments", "05_planning", "06_buckets"]:
        (ws / d).mkdir(parents=True, exist_ok=True)

    (ws / "00_definition" / "project_charter.json").write_text(
        json.dumps({"project_id": "PRJ-TEST-HD2"}), encoding="utf-8")
    (ws / "00_definition" / "stakeholder_matrix.json").write_text(
        json.dumps({"stakeholders": []}), encoding="utf-8")

    # 세그먼트 파일 생성
    segments = []
    topics = [
        ("온실가스 배출량 Scope 1 직접배출 GRI 305-1", "SEG-00001"),
        ("용수 사용량 water consumption GRI 303-5", "SEG-00002"),
        ("산업안전보건 industrial safety GRI 403-9", "SEG-00003"),
    ]
    for i, (content, seg_id) in enumerate(topics[:num_files]):
        seg_file = ws / "04_segments" / f"{seg_id}.md"
        seg_file.write_text(f"---\nsegment_id: {seg_id}\nsource_file_id: F-{i+1:04d}\nheading_path: {content.split()[0]}\n---\n\n{content}\n", encoding="utf-8")
        segments.append({
            "segment_id": seg_id,
            "source_file_id": f"F-{i+1:04d}",
            "heading_path": content.split()[0],
            "file_path": f"04_segments/{seg_id}.md",
            "content_preview": content[:500],
        })

    (ws / "04_segments" / "segment_manifest.json").write_text(
        json.dumps({"segments": segments}, ensure_ascii=False, indent=2), encoding="utf-8")

    return ws

def test_segment_manifest_has_file_path():
    """HD-1 이후 생성된 segment_manifest의 모든 엔트리에 file_path가 있어야 한다."""
    from scripts.run_ingestion import run_ingestion
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "PRJ-TEST-HD2-ING"
        for d in ["00_definition", "01_raw", "02_file_registry",
                   "03_normalized_md", "04_segments"]:
            (ws / d).mkdir(parents=True, exist_ok=True)
        (ws / "00_definition" / "project_charter.json").write_text(
            json.dumps({"project_id": "test"}), encoding="utf-8")
        (ws / "00_definition" / "stakeholder_matrix.json").write_text(
            json.dumps({"stakeholders": []}), encoding="utf-8")

        f = ws / "01_raw" / "ghg_report.txt"
        f.write_text("# 온실가스 배출량\n\nScope 1 배출량은 12,345 tCO2e입니다.", encoding="utf-8")

        run_ingestion(ws, [str(f)])

        manifest = json.loads((ws / "04_segments" / "segment_manifest.json").read_text())
        for seg in manifest.get("segments", []):
            assert "file_path" in seg, f"file_path missing in {seg['segment_id']}"
            assert "content_preview" in seg, f"content_preview missing in {seg['segment_id']}"

def test_grounded_bucket_has_nonzero_confidence():
    """segments가 매칭된 bucket은 confidence > 0이어야 한다."""
    # 이 테스트는 _find_segments_for_section이 제대로 매칭하는지 확인
    # 실제 structure_index + blueprint가 필요하므로
    # _build_buckets_from_structure_index를 직접 호출하여 테스트
    pass  # 구현 시 workspace fixture와 함께 작성

def test_empty_bucket_has_zero_confidence():
    """segments가 없는 bucket은 confidence=0.0이어야 한다."""
    pass  # 구현 시 작성
```

### Acceptance Criteria
1. `segment_manifest.json`의 모든 엔트리에 `file_path`와 `content_preview` 존재
2. 3개 이상 주제가 다른 세그먼트가 있을 때, grounded bucket이 최소 1개 이상 생성
3. segments가 없는 bucket의 confidence는 정확히 0.0
4. 기존 테스트 전부 통과

---

## HD-3: Writer Contract Enforcement

### 문제 (AUD-2 Finding F3)
`dispatch_agent.py`가 LLM 응답 내용을 검증하지 않아, 대기 메시지나 provenance tag가 0개인 응답도 success로 저장된다.

### 설계 기준
`purrfect-riding-blossom.md` §2.5: "모든 문장에 `<!-- src:SEG-XXXXX@vN -->` 또는 `<!-- src:CALC-XXXX -->` 태그 필수". 태그 없는 grounded draft는 실패로 처리해야 한다.

### 수정 대상
1. `scripts/run_section_writer.py` — grounded draft validation
2. `scripts/dispatch_agent.py` — 빈 응답/대기 응답 감지

### 현재 코드 구조

**write_single_section()** (line 746-854):
- line 780-790: `_is_fallback_bucket()` 체크 → fallback이면 `_generate_fallback_draft()` 호출
- line 795-810: grounded 경로 → `dispatcher.dispatch()` → LLM 응답 수신
- line 806-807: `save_draft()` / `save_draft_meta()` 호출

**dispatch()** in dispatch_agent.py (line 134-226):
- line 187: LLM 호출
- line 190-191: 출력 파일 쓰기
- line 249 부근: 응답 텍스트 반환
- **응답 내용 검증 없음**

**validate_and_enforce_source_tags()** (line 464-499):
- 이미 구현되어 있으나, write_single_section의 grounded 경로에서 호출 후에도 tag 0개이면 그대로 진행

### 구현 지시

#### Part A: dispatch_agent.py — 빈 응답 감지

**Step 1**: `dispatch()` 메서드 (line 134-226)에서 LLM 응답 수신 후 (line ~187-191), 최소 품질 체크 추가:

```python
# LLM 응답 최소 품질 체크
EMPTY_RESPONSE_PATTERNS = [
    "대기 상태",
    "대기중",
    "waiting for",
    "no content available",
    "아직 작성되지 않았습니다",
]

def _is_empty_or_waiting_response(text: str) -> bool:
    """LLM 응답이 실질적 내용 없는 대기/빈 응답인지 판별."""
    stripped = text.strip()
    if len(stripped) < 50:
        return True
    text_lower = stripped.lower()
    for pattern in EMPTY_RESPONSE_PATTERNS:
        if pattern in text_lower:
            return True
    return False
```

**Step 2**: `dispatch()` 내에서 응답 체크 후, 빈 응답이면 1회 재시도:

```python
llm_result = self._call_llm(full_prompt, agent)
if _is_empty_or_waiting_response(llm_result.text):
    # 1회 재시도
    llm_result = self._call_llm(full_prompt, agent)
    if _is_empty_or_waiting_response(llm_result.text):
        return DispatchResult(
            success=False,
            agent=agent,
            output_text=llm_result.text,
            error="LLM returned empty/waiting response after retry",
        )
```

#### Part B: run_section_writer.py — grounded draft source tag 검증

**Step 1**: `write_single_section()` (line 746-854)에서, grounded 경로의 LLM 응답 수신 후 (`validate_and_enforce_source_tags()` 호출 후):

```python
# grounded draft source tag 검증
import re
PROVENANCE_TAG_RE = re.compile(r"<!--\s*src:(SEG-\d+|CALC-\d+)")

def _count_source_tags(body: str) -> int:
    return len(PROVENANCE_TAG_RE.findall(body))
```

**Step 2**: grounded 경로에서 tag validation 삽입 (validate_and_enforce_source_tags 호출 직후):

```python
# validate_and_enforce_source_tags 호출 후
enforced_body, enforcement_meta = validate_and_enforce_source_tags(
    workspace, section_id, body, bucket_data)

tag_count = _count_source_tags(enforced_body)
if tag_count == 0 and not _is_fallback_bucket(bucket_data):
    # grounded bucket인데 source tag가 0개 → 초안 실패
    meta["grounding_mode"] = "failed"
    meta["draft_confidence"] = 0.0
    meta["failure_reason"] = "grounded_bucket_but_no_source_tags"
    # 실패한 초안은 저장하되 status를 failed로 표기
    meta["draft_status"] = "failed"
    # blocking issue 등록
    if state_manager:
        state_manager.add_blocking_issue({
            "issue_id": f"BLK-WRITER-{section_id}",
            "phase": "P4",
            "description": f"{section_id}: grounded bucket이나 source tag 0개. LLM 응답 품질 문제.",
            "severity": "high",
        })
```

**Step 3**: draft meta에 `grounding_mode` 필드 추가 (모든 경로):
- fallback 경로: `"grounding_mode": "fallback"`
- grounded 성공: `"grounding_mode": "grounded"`
- grounded 실패: `"grounding_mode": "failed"`

### 테스트 추가

`tests/test_writer_contract.py` 신규:

```python
"""HD-3: Writer contract — grounded draft without source tags → failed."""

def test_empty_response_detected():
    """빈/대기 응답이 감지되어야 한다."""
    from scripts.dispatch_agent import _is_empty_or_waiting_response
    assert _is_empty_or_waiting_response("대기 상태입니다.") is True
    assert _is_empty_or_waiting_response("짧음") is True
    assert _is_empty_or_waiting_response("## 온실가스 배출량\n\n당사의 Scope 1 배출량은...이며 <!-- src:SEG-00001 --> 전년 대비 감소했습니다.") is False

def test_grounding_mode_in_meta():
    """draft meta에 grounding_mode 필드가 있어야 한다."""
    # fallback draft 생성 후 meta 확인
    from scripts.run_section_writer import _generate_fallback_draft
    body, meta = _generate_fallback_draft(
        "SEC-3.1", {"depth_level": 3, "title": "테스트"}, {"section_id": "SEC-3.1"})
    assert meta.get("grounding_mode") == "fallback" or meta.get("fallback_mode") is True
```

### Acceptance Criteria
1. `dispatch_agent.py`: 50자 미만 또는 "대기 상태" 패턴 응답 → 1회 재시도 후 실패 반환
2. `write_single_section()`: grounded bucket에서 source tag 0개 → `draft_status: "failed"`, blocking issue 등록
3. 모든 draft meta에 `grounding_mode` 필드 존재 (`"grounded"` | `"fallback"` | `"failed"`)
4. 기존 테스트 통과

---

## HD-4: Pipeline Status Sync

### 문제 (AUD-2 Finding F4)
`run_pipeline.py`의 main path에서 `engine.run()` 반환 후 파생 상태 요약(blocking_issues, next_actions, project_state)이 갱신되지 않아, `status` 명령이 stale 데이터를 보여준다.

### 설계 기준
`purrfect-riding-blossom.md` §1.5: "파생 상태 요약은 매 작업 완료시 갱신"

### 수정 대상
1. `scripts/utils.py` — `sync_workspace()` 헬퍼 추가
2. `scripts/run_pipeline.py` — 완료 후 sync 호출
3. `llm/cli.py` — pipeline 후 status 자동 출력

### 현재 코드 구조

**run_pipeline.py** (line 858-869):
- `rebuild_blocking_issues()` + `rebuild_next_actions()` 호출이 있으나, 성공 시에만 (line 860 조건문)
- 실패 시 호출 안 됨

**llm/cli.py cmd_run_pipeline()** (line 343-418):
- line 413: `result = engine.run()`
- line 414: `engine.print_summary(result)`
- line 415: `return 0 if result.success else 1`
- `cmd_status()` 호출 없음, `rebuild_*` 호출 없음

**rebuild_summaries.py**:
- `rebuild_blocking_issues(workspace)` (line 595)
- `rebuild_next_actions(workspace, blocking_issues)` (line 632)

**update_project_state.py**:
- 전체 project_state.json을 재생성하는 스크립트

### 구현 지시

#### Step 1: scripts/utils.py에 sync_workspace() 추가

```python
from pathlib import Path

def sync_workspace(workspace: Path) -> dict:
    """워크스페이스의 모든 파생 상태 요약을 재생성한다.

    모든 mutating operation 완료 후 호출해야 한다.
    Returns: {"blocking_issues": int, "next_actions": int, "project_state": bool}
    """
    from scripts.rebuild_summaries import (
        rebuild_blocking_issues,
        rebuild_next_actions,
    )
    from scripts.update_project_state import update_project_state

    result = {}

    # 1) blocking issues 재생성
    bi = rebuild_blocking_issues(workspace)
    issues = bi.get("issues", [])
    result["blocking_issues"] = len(issues)

    # 2) next actions 재생성
    na = rebuild_next_actions(workspace, issues)
    result["next_actions"] = len(na.get("actions", []))

    # 3) project_state 재생성
    try:
        update_project_state(workspace)
        result["project_state"] = True
    except Exception:
        result["project_state"] = False

    return result
```

#### Step 2: run_pipeline.py — 완료 후 무조건 sync

`run_pipeline.py`의 `engine.run()` 메서드 (line 566) 말미에서, **성공/실패 무관하게** sync_workspace 호출:

현재 (line 858-869 부근):
```python
# 성공 시에만 rebuild
if result.success:
    blocking = rebuild_blocking_issues(workspace)
    ...
```

수정:
```python
# 성공/실패 무관하게 항상 sync
finally:
    try:
        from scripts.utils import sync_workspace
        sync_workspace(self.workspace)
    except Exception as e:
        # sync 실패가 pipeline 결과를 바꾸면 안 됨
        import logging
        logging.getLogger(__name__).warning(f"sync_workspace failed: {e}")
```

기존의 성공 시에만 호출하던 `rebuild_blocking_issues()` + `rebuild_next_actions()` 블록은 제거하고 `sync_workspace()`로 대체.

#### Step 3: llm/cli.py — pipeline 후 status 출력

`cmd_run_pipeline()` (line 343-418)에서, pipeline 완료 후:

```python
result = engine.run()
engine.print_summary(result)

# 최종 상태 자동 출력
try:
    from scripts.update_project_state import generate_narrative_status
    narrative = generate_narrative_status(workspace)
    if narrative:
        click.echo("\n--- Current Status ---")
        click.echo(narrative)
except Exception:
    pass  # status 출력 실패가 exit code에 영향 주면 안 됨

return 0 if result.success else 1
```

### 테스트 추가

`tests/test_pipeline_sync.py` 신규:

```python
"""HD-4: Pipeline 완료 후 status sync."""

def test_sync_workspace_creates_all_summaries():
    """sync_workspace가 3개 파생 파일을 모두 갱신해야 한다."""
    import json, tempfile
    from pathlib import Path
    from scripts.utils import sync_workspace

    # 최소 워크스페이스 생성 (project_state 재생성 가능한 수준)
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp) / "PRJ-TEST-HD4"
        for d in ["00_definition", "01_raw", "02_file_registry",
                   "03_normalized_md", "04_segments", "05_planning",
                   "06_buckets", "07_drafts", "08_review",
                   "09_handoff", "10_evidence_pack", "context_bus"]:
            (ws / d).mkdir(parents=True, exist_ok=True)
        (ws / "00_definition" / "project_charter.json").write_text(
            json.dumps({"project_id": "test"}), encoding="utf-8")
        (ws / "00_definition" / "stakeholder_matrix.json").write_text(
            json.dumps({"stakeholders": []}), encoding="utf-8")

        result = sync_workspace(ws)
        assert "blocking_issues" in result
        assert "next_actions" in result
        assert (ws / "blocking_issues.json").exists()
        assert (ws / "next_actions.json").exists()
```

### Acceptance Criteria
1. `sync_workspace()` 함수가 `scripts/utils.py`에 존재
2. pipeline 성공/실패 후 모두 `blocking_issues.json`, `next_actions.json` 재생성됨
3. pipeline 완료 후 CLI에 현재 상태 narrative 자동 출력
4. sync 실패가 pipeline exit code에 영향 안 줌
5. 기존 테스트 통과

---

## HD-5: Draft Query Typed Fields

### 문제 (AUD-2 Finding F5)
placeholder에서 자동 생성된 draft query에 `query_type`, `context`, `related_segments`가 누락되어, 컨설턴트에게 유용한 정보를 제공하지 못한다.

### 설계 기준
`purrfect-riding-blossom.md` §2.5: draft_queries.json의 각 항목에 `query_type` (5종), `context`, `related_segments`, `priority` 필수.

### 수정 대상
`scripts/run_section_writer.py`

### 현재 코드 구조

**_extract_draft_queries_from_content()** (line 299-325):
- placeholder `[확인필요: ...]` 패턴을 파싱하여 DQ 생성
- 현재 생성되는 필드: `query_id`, `section_id`, `question`, `priority`, `status`, `created_at`
- **누락 필드**: `query_type`, `context`, `related_segments`

**_locked_draft_queries_update()** (line 234-247):
- 신규 DQ를 `draft_queries.json`에 thread-safe하게 추가
- DQ 구조를 변경하지 않고 그대로 저장

### 구현 지시

#### Step 1: query_type 추론 함수 추가

```python
def _infer_query_type(question: str) -> str:
    """placeholder 텍스트에서 query_type을 추론한다.

    5종: data_confirmation, additional_data_request,
         numeric_discrepancy, policy_clarification, scope_question
    """
    q_lower = question.lower()

    # 수치 불일치 키워드
    if any(kw in q_lower for kw in ["불일치", "차이", "다른 수치", "discrepancy", "mismatch"]):
        return "numeric_discrepancy"

    # 추가 자료 요청 키워드
    if any(kw in q_lower for kw in ["추가", "필요", "미확보", "누락", "없습니다", "부족", "미제출"]):
        return "additional_data_request"

    # 범위/경계 키워드
    if any(kw in q_lower for kw in ["범위", "경계", "scope", "boundary", "포함 여부"]):
        return "scope_question"

    # 정책/제도 키워드
    if any(kw in q_lower for kw in ["정책", "제도", "절차", "규정", "방침", "policy"]):
        return "policy_clarification"

    # 기본값: 데이터 확인
    return "data_confirmation"
```

#### Step 2: context 추출 함수 추가

```python
def _extract_query_context(body: str, placeholder_text: str) -> str:
    """placeholder 주변 문맥 (앞뒤 1문장)을 추출한다."""
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if placeholder_text in line:
            context_lines = []
            if i > 0:
                context_lines.append(lines[i - 1].strip())
            context_lines.append(line.strip())
            if i < len(lines) - 1:
                context_lines.append(lines[i + 1].strip())
            return " ".join(context_lines)[:300]
    return ""
```

#### Step 3: _extract_draft_queries_from_content() 수정

현재 DQ 생성 부분 (line ~310-325)에서 각 DQ dict에 3개 필드 추가:

```python
query = {
    "query_id": query_id,
    "query_type": _infer_query_type(question_text),          # 추가
    "section_id": section_id,
    "question": question_text,
    "context": _extract_query_context(body, match.group(0)),  # 추가
    "related_segments": _get_related_segments(bucket_data),    # 추가
    "priority": priority,
    "status": "open",
    "created_at": datetime.utcnow().isoformat() + "Z",
}
```

#### Step 4: related_segments 헬퍼

```python
def _get_related_segments(bucket_data: Optional[dict]) -> list[str]:
    """bucket에서 관련 segment ID 목록을 추출한다."""
    if not bucket_data:
        return []
    segments = bucket_data.get("segments", [])
    return [s.get("segment_id", "") for s in segments if s.get("segment_id")]
```

#### Step 5: _extract_draft_queries_from_content 시그니처 수정

현재 시그니처에 `bucket_data`와 `body` 파라미터가 없다면 추가:
```python
def _extract_draft_queries_from_content(
    content: str,
    section_id: str,
    bucket_data: Optional[dict] = None,   # 추가
) -> list[dict]:
```

호출부도 함께 수정 (write_single_section 내에서 bucket_data를 전달).

#### Step 6: source_tag_violation DQ도 typed fields 추가

`_register_source_tag_violations()` (line 390-461)에서 생성하는 DQ에도 동일하게:
- `query_type: "source_tag_violation"` (기존 유지)
- `context`: 해당 문단 텍스트 첫 200자
- `related_segments`: bucket의 segment IDs

### 테스트 추가

`tests/test_draft_queries_typed.py` 신규:

```python
"""HD-5: Draft query typed fields."""

def test_infer_query_type():
    from scripts.run_section_writer import _infer_query_type

    assert _infer_query_type("Scope 3 데이터 미확보") == "additional_data_request"
    assert _infer_query_type("두 출처 간 수치 불일치") == "numeric_discrepancy"
    assert _infer_query_type("보고 범위에 해외 사업장 포함 여부") == "scope_question"
    assert _infer_query_type("환경 정책 존재 여부 확인") == "policy_clarification"
    assert _infer_query_type("기준연도 확인 필요") == "data_confirmation"

def test_extract_query_context():
    from scripts.run_section_writer import _extract_query_context

    body = "전년도 대비 배출량이 감소했습니다.\n[확인필요: Scope 3 데이터 미확보]\n추가 자료가 필요합니다."
    ctx = _extract_query_context(body, "[확인필요: Scope 3 데이터 미확보]")
    assert "전년도" in ctx
    assert "Scope 3" in ctx
    assert "추가 자료" in ctx

def test_draft_query_has_all_typed_fields():
    """생성된 DQ에 query_type, context, related_segments가 있어야 한다."""
    from scripts.run_section_writer import _extract_draft_queries_from_content

    content = "## 온실가스\n\n배출량 데이터입니다.\n[확인필요: Scope 1 데이터 확인 필요]\n종료."
    bucket = {"segments": [{"segment_id": "SEG-00001"}, {"segment_id": "SEG-00002"}]}
    queries = _extract_draft_queries_from_content(content, "SEC-3.1", bucket)

    assert len(queries) >= 1
    q = queries[0]
    assert "query_type" in q and q["query_type"] in [
        "data_confirmation", "additional_data_request",
        "numeric_discrepancy", "policy_clarification", "scope_question"]
    assert "context" in q and len(q["context"]) > 0
    assert "related_segments" in q and isinstance(q["related_segments"], list)
```

### Acceptance Criteria
1. placeholder에서 생성된 모든 DQ에 `query_type`, `context`, `related_segments` 존재
2. `query_type`이 5종 중 하나로 올바르게 추론됨
3. `context`가 placeholder 주변 문맥을 포함
4. `related_segments`가 bucket의 segment IDs를 반영
5. 기존 테스트 통과

---

## 완료 조건

모든 HD-1~HD-5가 DONE이면, **AUD-2의 6개 findings가 모두 해결**된다.

이후 선택적으로:
- **Realistic fixture로 E2E 검증**: 5+ 파일, 20+ 세그먼트 투입 후 grounded bucket > 30% + grounded draft에 source tag 존재 확인
- **SR-1~SR-3 구조 개선**: artifact model 통합, sync_workspace 전면 적용, CI fixture

---

## 참조 파일

| 파일 | 역할 |
|------|------|
| `purrfect-riding-blossom.md` | 최초 설계 문서 (진실의 원천) |
| `IMPLEMENTATION_PROGRESS.md` | 기존 OD-1~OD-10 이력 |
| `SESSION_LOG.md` | 세션별 작업 로그 |
| `CLAUDE.md` | 오케스트레이터 헌법 |
| `orchestration/phase_rules.json` | 페이즈 규칙 |
| `orchestration/gate_rules.json` | 게이트 규칙 |
