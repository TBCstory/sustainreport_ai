# PKT-A002 — P1 ingestion → normalize.py 통합 + data_gap_report.json 생성

## 개요

**문제**: `run_ingestion.py`가 파일 변환 시 `run_markitdown()` 함수를 직접 호출하고 있어서, PKT-002에서 구현된 `normalize.py`의 HWP/OCR 자동 라우팅이 P1 메인 경로에서 전혀 사용되지 않는다. 또한 `data_gap_report.json`과 `unconvertible_files.json`이 실제로 생성되지 않는다.

**효과**: 이 패킷 완료 후 `run_ingestion.py` 실행 시 HWP는 kordoc로, 스캔 PDF는 tesseract로 자동 변환되며, YAML `conversion_method` 헤더가 정확히 기록된다. ingestion 완료 후 `data_gap_report.json`이 자동 생성된다.

---

## 입력 파일 (작업 전 반드시 읽기)

1. `scripts/run_ingestion.py` — 전체 (특히 `run_ingestion()` 함수의 파일 처리 루프)
2. `scripts/normalize.py` — `process_single_file()` 함수 시그니처와 반환값 구조
3. `schemas/data_gap_report.schema.json` — data_gap_report의 JSON 스키마
4. `orchestration/agent_contracts.json` — data-analyst의 출력 계약 확인

---

## 상세 작업

### 작업 1. `scripts/run_ingestion.py` — import 추가

**백업 먼저**: `cp scripts/run_ingestion.py scripts/run_ingestion.py.bak`

파일 상단 import 섹션에 추가:
```python
from scripts.normalize import process_single_file
```

---

### 작업 2. 파일 처리 루프 교체

`run_ingestion()` 함수 내의 파일 처리 루프에서 `run_markitdown()` 직접 호출 부분(line ~409)을 찾는다.

현재 코드 패턴:
```python
# markitdown 변환
success, error_msg = run_markitdown(file_path, normalized_path)

if success:
    # ... 세그먼트 추출 및 registry 기록
else:
    # 변환 실패 처리
```

이 블록 전체를 아래와 같이 교체한다:

```python
# normalize.py를 통한 자동 라우팅 변환 (HWP/OCR/markitdown 자동 선택)
conversion_method = "unknown"
convert_success = False
convert_error = None

try:
    norm_result = process_single_file(
        input_path=file_path,
        output_path=normalized_path,
        workspace_path=workspace,
        extract_segments=False,   # 세그먼트 추출은 아래에서 별도 처리
        force=True,               # 이미 존재해도 덮어쓰기
        force_ocr=False,          # 스캔 감지는 자동 (필요 시 CLI로 --force-ocr 가능)
    )
    conversion_method = norm_result.get("conversion_method", "markitdown")
    convert_success = True
except (FileNotFoundError, ValueError, RuntimeError) as e:
    convert_error = str(e)
    convert_success = False

if convert_success:
    # 세그먼트 추출
    try:
        segments, current_segment_num = split_segments(
            normalized_path, segments_dir, file_id, workspace, current_segment_num
        )
        segments_created += len(segments)

        # file_registry 항목 추가
        registry_data["files"].append(
            {
                "file_id": file_id,
                "source_path": str(file_path.relative_to(workspace)),
                "file_type": get_file_type(file_path),
                "converted_path": str(normalized_path.relative_to(workspace)),
                "conversion_status": "success",
                "conversion_method": conversion_method,   # ← 신규 필드
                "conversion_error": None,
                "content_hash": content_hash,
                "metadata": {
                    "title": file_path.stem,
                    "author": None,
                    "page_count": None,
                    "converted_at": utc_now(),
                },
                "segments_count": len(segments),
                "ingested_at": utc_now(),
            }
        )

        files_success += 1
        outputs.append(str(normalized_path.relative_to(workspace)))

    except Exception as e:
        errors.append(f"Segment extraction failed for {file_id}: {e}")
        files_failed += 1
        registry_data["files"].append(
            {
                "file_id": file_id,
                "source_path": str(file_path.relative_to(workspace)),
                "file_type": get_file_type(file_path),
                "converted_path": str(normalized_path.relative_to(workspace)),
                "conversion_status": "partial",
                "conversion_method": conversion_method,   # ← 신규 필드
                "conversion_error": f"Segment extraction failed: {e}",
                "content_hash": content_hash,
                "metadata": {
                    "title": file_path.stem,
                    "author": None,
                    "page_count": None,
                    "converted_at": utc_now(),
                },
                "segments_count": 0,
                "ingested_at": utc_now(),
            }
        )
else:
    # 변환 실패 — unconvertible 목록에 추가
    errors.append(f"Conversion failed for {file_path.name}: {convert_error}")
    files_failed += 1
    registry_data["files"].append(
        {
            "file_id": file_id,
            "source_path": str(file_path.relative_to(workspace)),
            "file_type": get_file_type(file_path),
            "converted_path": None,
            "conversion_status": "failed",
            "conversion_method": None,
            "conversion_error": convert_error,
            "content_hash": content_hash,
            "metadata": {
                "title": file_path.stem,
                "author": None,
                "page_count": None,
                "converted_at": utc_now(),
            },
            "segments_count": 0,
            "ingested_at": utc_now(),
        }
    )
```

> **주의**: `process_single_file()`의 실제 반환 구조를 normalize.py에서 직접 확인하고 필드 이름을 맞춘다. `norm_result.get("conversion_method", "markitdown")` 키가 맞는지 확인 필수.

---

### 작업 3. `unconvertible_files.json` 생성

file_registry 저장 직후, `segment_manifest.json` 생성 전에 삽입:

```python
# unconvertible_files.json 생성
unconvertible = [
    {
        "file_id": f["file_id"],
        "source_path": f["source_path"],
        "file_type": f["file_type"],
        "conversion_error": f["conversion_error"],
    }
    for f in registry_data["files"]
    if f.get("conversion_status") == "failed"
]

unconvertible_path = workspace / "02_file_registry" / "unconvertible_files.json"
unconvertible_path.write_text(
    json.dumps(
        {
            "generated_at": utc_now(),
            "total_files": len(registry_data["files"]),
            "unconvertible_count": len(unconvertible),
            "files": unconvertible,
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n",
    encoding="utf-8",
)
outputs.append(str(unconvertible_path.relative_to(workspace)))
```

---

### 작업 4. `data_gap_report.json` 생성

`segment_manifest.json` 저장 후, `run_ingestion()` 함수 반환 직전에 삽입.

data_gap_report는 P1 시점에 알 수 있는 정보만 담는다 (writing_blueprint가 없으므로 섹션별 분석은 불가):

```python
# data_gap_report.json 생성
total_files = len(registry_data["files"])
success_files = [f for f in registry_data["files"] if f.get("conversion_status") == "success"]
partial_files = [f for f in registry_data["files"] if f.get("conversion_status") == "partial"]
failed_files = [f for f in registry_data["files"] if f.get("conversion_status") == "failed"]

# 변환 방법별 분류
method_breakdown: dict[str, int] = {}
for f in registry_data["files"]:
    method = f.get("conversion_method") or "unknown"
    method_breakdown[method] = method_breakdown.get(method, 0) + 1

# 파일 유형별 분류
type_breakdown: dict[str, dict] = {}
for f in registry_data["files"]:
    ftype = f.get("file_type", "unknown")
    if ftype not in type_breakdown:
        type_breakdown[ftype] = {"total": 0, "success": 0, "failed": 0}
    type_breakdown[ftype]["total"] += 1
    if f.get("conversion_status") == "success":
        type_breakdown[ftype]["success"] += 1
    elif f.get("conversion_status") == "failed":
        type_breakdown[ftype]["failed"] += 1

data_gap_report = {
    "generated_at": utc_now(),
    "phase": "P1",
    "summary": {
        "total_files": total_files,
        "converted_success": len(success_files),
        "converted_partial": len(partial_files),
        "conversion_failed": len(failed_files),
        "total_segments": segments_created,
        "conversion_rate": round(len(success_files) / total_files, 3) if total_files > 0 else 0,
    },
    "conversion_method_breakdown": method_breakdown,
    "file_type_breakdown": type_breakdown,
    "unconvertible_files": [
        {
            "file_id": f["file_id"],
            "source_path": f["source_path"],
            "file_type": f["file_type"],
            "error": f.get("conversion_error"),
        }
        for f in failed_files
    ],
    "notes": [
        "섹션별 자료 충족도는 writing_blueprint 생성(P2) 후 framework-mapper 단계에서 보완됩니다.",
        f"처리 불가 파일 {len(failed_files)}개가 있습니다. 컨설턴트에게 수동 변환 또는 대체 자료 제공을 요청하세요."
        if failed_files else "모든 파일이 정상 변환됐습니다.",
    ],
}

gap_report_path = workspace / "02_file_registry" / "data_gap_report.json"
gap_report_path.write_text(
    json.dumps(data_gap_report, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
outputs.append(str(gap_report_path.relative_to(workspace)))
```

---

### 작업 5. 기존 `run_markitdown()` 함수 보존 여부 확인

`run_markitdown()` 함수가 run_ingestion.py 내에 로컬 함수로 정의돼 있다면:
- 테스트에서 mock으로 사용되고 있을 가능성이 있으므로 **삭제하지 않는다**
- 단, 메인 루프에서 더 이상 호출되지 않는다

`run_markitdown()` 함수가 외부 모듈에서 import된 것이라면:
- import 라인을 주석 처리하거나 제거한다 (사용되지 않으면 lint 경고)

---

## 완료 기준 체크리스트

```bash
# 1. 테스트용 워크스페이스에서 ingestion 실행
uv run python scripts/run_ingestion.py --workspace workspaces/PRJ-2026-KRS-001

# 2. 변환 방법 기록 확인 — conversion_method 필드가 있어야 함
# 03_normalized_md/F-0001.md의 YAML 헤더에 conversion_method 확인
head -20 workspaces/PRJ-2026-KRS-001/03_normalized_md/F-0001.md

# 3. data_gap_report.json 생성 확인
ls -la workspaces/PRJ-2026-KRS-001/02_file_registry/data_gap_report.json
cat workspaces/PRJ-2026-KRS-001/02_file_registry/data_gap_report.json

# 4. unconvertible_files.json 생성 확인
ls -la workspaces/PRJ-2026-KRS-001/02_file_registry/unconvertible_files.json

# 5. 기존 테스트 회귀 없음 확인
uv run pytest tests/ -x -q
```

---

## 결정 원칙

- `process_single_file()`의 반환 구조에서 `conversion_method` 필드 키는 normalize.py를 직접 읽어서 확인한다. `norm_result.get("conversion_method")`가 아니라 다른 키일 수 있다.
- P1 시점의 data_gap_report는 "파일이 변환됐는가"만 판정한다. 섹션별 자료 충족도 분석은 P2 이후 별도 태스크로 남겨둔다.
- `files_failed`가 0이어도 `unconvertible_files.json`은 빈 리스트로 생성한다 (존재 여부가 상태 판정에 사용됨).
