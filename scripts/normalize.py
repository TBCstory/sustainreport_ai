#!/usr/bin/env python3.13
"""
파일 정규화 스크립트 — markitdown 래핑 + 구조화된 markdown 변환

지원 형식: PDF, DOCX, HWP, HWPX, TXT, MD, XLSX, CSV, HTML

변환 경로:
  PDF (일반)  → markitdown (pdfplumber/pdfminer)
  PDF (스캔본) → OCR 자동 감지 → tesseract 또는 LLM OCR (ocr_convert.py)
  HWP/HWPX   → kordoc Node.js CLI (hwp_convert.py)
  DOCX/XLSX  → markitdown
  TXT/MD/CSV → 직접 읽기

사용법:
  # 단일 파일 변환 (PDF 스캔 자동 감지, HWP 자동 라우팅)
  python scripts/normalize.py --input /path/to/report.pdf --output /path/to/output.md

  # 배치 변환 (file_registry 기반)
  python scripts/normalize.py --workspace /path/to/PRJ-YYYY-CODE-NNN --batch

  # 세그먼트 추출 포함
  python scripts/normalize.py --input /path/to/report.pdf --output /path/to/output.md --extract-segments

  # OCR 강제 적용 (스캔 여부 체크 없이)
  python scripts/normalize.py --input /path/to/scanned.pdf --output out.md --force-ocr
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".hwp", ".hwpx", ".txt", ".md", ".xlsx", ".csv", ".html"}

REGISTRY_FILENAME = "file_registry.json"
NEXT_ID_FILE = "next_file_id.json"
NEXT_SEGMENT_ID_FILE = "next_segment_id.json"


def check_markitdown_installed() -> bool:
    """markitdown CLI 설치 여부 확인"""
    try:
        result = subprocess.run(["markitdown", "--version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def resolve_markitdown_command() -> str | None:
    """Resolve markitdown without relying on ambient PATH alone."""
    import shutil

    executable_name = "markitdown.exe" if sys.platform == "win32" else "markitdown"
    candidates = [
        Path(sys.executable).resolve().parent / executable_name,
        Path(__file__).parent.parent / ".venv" / "bin" / executable_name,
        Path(__file__).parent.parent / ".venv" / "Scripts" / executable_name,
    ]
    seen: set[str] = set()
    for candidate in candidates:
        candidate_str = str(candidate.resolve())
        if candidate_str in seen:
            continue
        seen.add(candidate_str)
        if candidate.is_file():
            return candidate_str
    return shutil.which("markitdown")


def convert_with_markitdown(input_path: Path, output_path: Path) -> dict[str, str]:
    """markitdown CLI 호출 래퍼"""
    command = resolve_markitdown_command()
    if not command:
        raise RuntimeError("markitdown command not found")
    result = subprocess.run([command, str(input_path), "-o", str(output_path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"markitdown 실패: {result.stderr}")
    return {"status": "success", "output": str(output_path)}


def convert_with_hwp(input_path: Path, output_path: Path) -> dict[str, Any]:
    """HWP/HWPX 변환 — hwp_convert.py (kordoc 래퍼) 호출"""
    scripts_dir = Path(__file__).parent
    hwp_script = scripts_dir / "hwp_convert.py"

    result = subprocess.run(
        [sys.executable, str(hwp_script), "--input", str(input_path), "--output", str(output_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
        with open(output_path, encoding="utf-8") as f:
            char_count = len(f.read().strip())
        return {"status": "success", "method": "kordoc", "char_count": char_count}
    else:
        err = result.stderr.strip() or result.stdout.strip()
        # kordoc/Node.js 미설치 시 사용자가 수동 변환한 .md가 있는지 확인
        manual_md = input_path.with_suffix(".md")
        if manual_md.exists():
            import shutil

            shutil.copy2(manual_md, output_path)
            with open(output_path, encoding="utf-8") as f:
                char_count = len(f.read().strip())
            return {
                "status": "success",
                "method": "manual_md_copy",
                "char_count": char_count,
                "note": f"동일 이름 .md 파일 사용 ({manual_md.name})",
            }
        raise RuntimeError(
            f"HWP 변환 실패: {err[:200]}\n"
            "해결 방법:\n"
            "  1. brew install node && npm install -g kordoc\n"
            "  2. 또는 동일한 이름의 .md 파일을 같은 디렉토리에 수동 생성"
        )


def convert_with_ocr(input_path: Path, output_path: Path, force_ocr: bool = False) -> dict[str, Any]:
    """스캔본 PDF OCR 변환 — ocr_convert.py 호출"""
    scripts_dir = Path(__file__).parent
    ocr_script = scripts_dir / "ocr_convert.py"

    cmd = [sys.executable, str(ocr_script), "--input", str(input_path), "--output", str(output_path)]
    if force_ocr:
        cmd.append("--force-ocr")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode == 0:
        if "변환 불필요" in result.stdout:
            # 스캔본이 아님 → 일반 markitdown으로 재시도
            return {"status": "skipped", "reason": "not_scanned"}
        if output_path.exists() and output_path.stat().st_size > 0:
            with open(output_path, encoding="utf-8") as f:
                char_count = len(f.read().strip())
            return {"status": "success", "method": "ocr", "char_count": char_count}

    err = result.stderr.strip() or result.stdout.strip()
    raise RuntimeError(f"OCR 변환 실패: {err[:300]}")


def normalize_header_depth(content: str, remove_h1: bool = True) -> str:
    """헤더 정규화: # → ## (1단계 헤더 제거 또는 depth 조정)"""
    if remove_h1:
        lines = content.split("\n")
        result: list[str] = []
        for line in lines:
            if line.startswith("# "):
                result.append("##" + line[1:])
            else:
                result.append(line)
        return "\n".join(result)
    return content


def extract_metadata(content: str) -> dict[str, Any]:
    """메타데이터 추출: 제목, 작성일, 작성자, 테이블 구조, 이미지 참조"""
    metadata: dict[str, Any] = {
        "title": None,
        "author": None,
        "created_date": None,
        "tables_detected": 0,
        "images_referenced": 0,
    }

    lines = content.split("\n")
    for line in lines[:10]:
        if metadata["title"] is None and line.startswith("# "):
            metadata["title"] = line[2:].strip()
        if "![" in line:
            metadata["images_referenced"] = content.count("![")
            break

    # Count markdown table rows (lines containing |---| or similar table separator patterns)
    table_separator_pattern = content.count("\n| ---")
    metadata["tables_detected"] = max(table_separator_pattern, 0)

    return metadata


def split_into_segments(content: str, file_id: str, segment_start: int = 1) -> list[dict[str, Any]]:
    """세그먼트 분리: --- 또는 Heading 1 단위로 분리"""
    segments: list[dict[str, Any]] = []
    parts = content.split("\n---\n")

    segment_num = segment_start
    for part in parts:
        part = part.strip()
        if not part:
            continue

        heading_match = None
        heading_path = None

        for line in part.split("\n"):
            if line.startswith("# "):
                heading_match = line[2:].strip()
                heading_path = heading_match
                break

        segment_id = f"SEG-{segment_num:05d}"

        segments.append(
            {
                "segment_id": segment_id,
                "source_file_id": file_id,
                "heading_path": heading_path,
                "content": part,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        segment_num += 1

    return segments


def _count_segments(content: str) -> int:
    """Count how many segments would be created from content (without allocating IDs)."""
    parts = content.split("\n---\n")
    return sum(1 for part in parts if part.strip())


def extract_page_references(content: str) -> dict[str, str]:
    """페이지 참조 추출 (숫자 패턴 기반)"""
    import re

    references: dict[str, str] = {}
    pattern = r"p\.?\s*(\d+)"
    matches = re.findall(pattern, content, re.IGNORECASE)
    for idx, match in enumerate(matches[:10]):
        references[f"ref_{idx}"] = match
    return references


def load_file_registry(registry_path: Path) -> dict[str, Any]:
    """file_registry.json 로드"""
    if registry_path.exists():
        with open(registry_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"files": []}


def save_file_registry(registry_path: Path, data: dict[str, Any]) -> None:
    """file_registry.json 저장"""
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_next_file_id(workspace_path: Path) -> str:
    """다음 F-NNNN ID 생성"""
    id_file = workspace_path / "02_file_registry" / NEXT_ID_FILE

    if id_file.exists():
        with open(id_file, "r", encoding="utf-8") as f:
            current = json.load(f).get("current", 0)
    else:
        current = 0

    next_id = current + 1

    with open(id_file, "w", encoding="utf-8") as f:
        json.dump({"current": next_id}, f)

    return f"F-{next_id:04d}"


def get_next_segment_id(workspace_path: Path, count: int = 1) -> int:
    """다음 세그먼트 번호 반환 (글로벌 카운터)."""
    id_file = workspace_path / "04_segments" / NEXT_SEGMENT_ID_FILE

    if id_file.exists():
        with open(id_file, "r", encoding="utf-8") as f:
            current = json.load(f).get("next_id", 1)
    else:
        current = 1

    next_id = current + count
    with open(id_file, "w", encoding="utf-8") as f:
        json.dump({"next_id": next_id}, f)

    return current


def add_file_to_registry(workspace_path: Path, file_info: dict[str, Any]) -> None:
    """file_registry.json에 파일 정보 추가"""
    registry_path = workspace_path / "02_file_registry" / REGISTRY_FILENAME
    registry = load_file_registry(registry_path)

    existing = [f for f in registry.get("files", []) if f.get("file_id") == file_info.get("file_id")]
    if existing:
        for i, f in enumerate(registry["files"]):
            if f["file_id"] == file_info["file_id"]:
                registry["files"][i].update(file_info)
                break
    else:
        registry.setdefault("files", []).append(file_info)

    save_file_registry(registry_path, registry)


def process_single_file(
    input_path: Path,
    output_path: Path,
    workspace_path: Path | None = None,
    extract_segments: bool = False,
    force: bool = False,
    force_ocr: bool = False,
) -> dict[str, Any]:
    """단일 파일 변환 및 정규화

    변환 경로 자동 선택:
      .hwp/.hwpx → kordoc (Node.js) → 실패시 동명 .md 파일 사용
      .pdf → markitdown → 텍스트 밀도 낮으면 OCR 자동 전환
      기타  → markitdown
    """

    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {input_path}")

    ext = input_path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"지원하지 않는 형식입니다: {ext}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not force and output_path.exists():
        raise FileExistsError(f"출력 파일이 이미 존재합니다 (--force로 덮어쓰기): {output_path}")

    file_id = get_next_file_id(workspace_path) if workspace_path else "F-0001"

    # 변환 경로 분기
    conversion_meta: dict[str, Any] = {}

    if ext in {".hwp", ".hwpx"}:
        # HWP/HWPX → kordoc
        hwp_result = convert_with_hwp(input_path, output_path)
        conversion_meta["conversion_method"] = hwp_result.get("method", "kordoc")
        conversion_meta["conversion_note"] = hwp_result.get("note", "")
    elif ext == ".pdf":
        if force_ocr:
            # --force-ocr 플래그: markitdown 생략하고 바로 OCR
            ocr_result = convert_with_ocr(input_path, output_path, force_ocr=True)
            if ocr_result.get("status") == "success":
                conversion_meta["conversion_method"] = "ocr_forced"
            else:
                raise RuntimeError(f"강제 OCR 실패: {ocr_result.get('error', '')}")
        else:
            # PDF → markitdown 시도 후 스캔 감지 시 OCR 전환
            try:
                convert_with_markitdown(input_path, output_path)
                # 텍스트 밀도 체크
                if output_path.exists():
                    with open(output_path, encoding="utf-8") as f:
                        content_check = f.read().strip()
                    char_density = len(content_check) / max(input_path.stat().st_size / 1024, 1)
                    if len(content_check) < 100 or char_density < 10:
                        # 스캔본 가능성 → OCR 전환 시도
                        ocr_result = convert_with_ocr(input_path, output_path, force_ocr=True)
                        if ocr_result.get("status") == "success":
                            conversion_meta["conversion_method"] = "ocr_fallback"
                        else:
                            conversion_meta["conversion_method"] = "markitdown_low_density"
                            conversion_meta["ocr_attempted"] = True
                            conversion_meta["ocr_error"] = ocr_result.get("error", "")
                    else:
                        conversion_meta["conversion_method"] = "markitdown"
                else:
                    conversion_meta["conversion_method"] = "markitdown"
            except RuntimeError:
                # markitdown 실패 → OCR 마지막 시도
                ocr_result = convert_with_ocr(input_path, output_path, force_ocr=True)
                if ocr_result.get("status") == "success":
                    conversion_meta["conversion_method"] = "ocr_fallback"
                else:
                    raise
    else:
        convert_with_markitdown(input_path, output_path)
        conversion_meta["conversion_method"] = "markitdown"

    with open(output_path, "r", encoding="utf-8") as f:
        raw_content = f.read()

    normalized_content = normalize_header_depth(raw_content, remove_h1=True)

    metadata = extract_metadata(normalized_content)

    _title = metadata.get("title") or input_path.stem
    _author = metadata.get("author") or "Unknown"
    _conv_method = conversion_meta.get("conversion_method", "markitdown")
    header = f"""---
file_id: {file_id}
source_file: {input_path.name}
converted_at: {datetime.now(timezone.utc).isoformat()}
conversion_method: {_conv_method}
title: {_title}
author: {_author}
tables_detected: {metadata.get("tables_detected", 0)}
images_referenced: {metadata.get("images_referenced", 0)}
---

"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + normalized_content)

    result: dict[str, Any] = {
        "status": "success",
        "input": str(input_path),
        "output": str(output_path),
        "file_id": file_id,
        "metadata": metadata,
    }

    if extract_segments and workspace_path:
        # Two-phase ID allocation:
        # 1. Count segments from content to reserve ID range atomically
        # 2. Assign IDs within the reserved range
        segment_count = _count_segments(normalized_content)
        segment_start = get_next_segment_id(workspace_path, count=segment_count)
        segments = split_into_segments(normalized_content, file_id, segment_start=segment_start)
        segments_dir = workspace_path / "04_segments"
        segments_dir.mkdir(parents=True, exist_ok=True)

        for segment in segments:
            seg_path = segments_dir / f"{segment['segment_id']}.md"
            seg_content = f"""---
segment_id: {segment["segment_id"]}
source_file_id: {segment["source_file_id"]}
heading_path: "{segment["heading_path"]}"
page_reference: {segment.get("page_reference", "N/A")}
created_at: {segment["created_at"]}
---

{segment["content"]}
"""
            with open(seg_path, "w", encoding="utf-8") as f:
                f.write(seg_content)

        result["segments_count"] = len(segments)

    if workspace_path:
        file_info: dict[str, Any] = {
            "file_id": file_id,
            "source_path": str(input_path.relative_to(workspace_path)),
            "file_type": ext[1:],
            "converted_path": str(output_path.relative_to(workspace_path)),
            "conversion_status": "success",
            "conversion_error": None,
            "metadata": {
                "title": metadata.get("title", input_path.stem),
                "author": metadata.get("author", "Unknown"),
                "page_count": None,  # page count extraction not yet implemented
                "converted_at": datetime.now(timezone.utc).isoformat(),
            },
            "segments_count": result.get("segments_count", 0),
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        add_file_to_registry(workspace_path, file_info)
        result["registry_updated"] = True

    return result


def process_batch(workspace_path: Path, force: bool = False) -> list[dict[str, Any]]:
    """file_registry 기반 배치 변환"""
    registry_path = workspace_path / "02_file_registry" / REGISTRY_FILENAME
    registry = load_file_registry(registry_path)

    normalized_dir = workspace_path / "03_normalized_md"
    normalized_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    unconverted = [f for f in registry.get("files", []) if f.get("conversion_status") != "success" or force]

    for file_info in unconverted:
        source_path = workspace_path / file_info["source_path"]
        output_path = normalized_dir / f"{file_info['file_id']}.md"

        try:
            result = process_single_file(
                source_path, output_path, workspace_path=workspace_path, extract_segments=True, force=force
            )
            results.append(result)
        except Exception as e:
            error_result: dict[str, Any] = {
                "status": "failed",
                "file_id": file_info["file_id"],
                "source_path": str(source_path),
                "error": str(e),
            }
            results.append(error_result)

            file_info["conversion_status"] = "failed"
            file_info["conversion_error"] = str(e)
            add_file_to_registry(workspace_path, file_info)

    return results


@click.command()
@click.option("--input", "-i", "input_path", type=click.Path(exists=True), help="입력 파일 경로")
@click.option("--output", "-o", "output_path", type=click.Path(), help="출력 markdown 경로")
@click.option("--workspace", "-w", "workspace_path", type=click.Path(exists=True), help="워크스페이스 디렉토리 경로")
@click.option("--batch", "-b", is_flag=True, help="file_registry 기반 배치 변환 모드")
@click.option("--extract-segments", "-s", is_flag=True, help="세그먼트 추출 포함")
@click.option("--force", "-f", is_flag=True, help="이미 변환된 파일도 재변환")
@click.option("--force-ocr", is_flag=True, help="PDF를 텍스트 밀도 체크 없이 강제 OCR 변환")
def main(
    input_path: str | None,
    output_path: str | None,
    workspace_path: str | None,
    batch: bool,
    extract_segments: bool,
    force: bool,
    force_ocr: bool,
) -> None:
    """파일 정규화 스크립트 — markitdown 래핑 + 구조화된 markdown 변환"""

    if not check_markitdown_installed():
        click.echo("오류: markitdown이 설치되어 있지 않습니다.", err=True)
        click.echo("설치 명령: pip install markitdown", err=True)
        sys.exit(1)

    if batch:
        if not workspace_path:
            click.echo("오류: --batch 모드에서는 --workspace가 필요합니다.", err=True)
            sys.exit(1)

        ws = Path(workspace_path)
        results = process_batch(ws, force=force)

        click.echo(f"\n배치 변환 완료: {len(results)}개 파일 처리")
        for r in results:
            status = r.get("status", "unknown")
            file_id_val = r.get("file_id", r.get("source_path", "unknown"))
            segments = r.get("segments_count", 0)
            click.echo(f"  [{status}] {file_id_val}" + (f" ({segments} segments)" if segments else ""))

        failed = [r for r in results if r.get("status") == "failed"]
        if failed:
            sys.exit(1)

    elif input_path:
        if not output_path:
            click.echo("오류: --input 사용 시 --output이 필요합니다.", err=True)
            sys.exit(1)

        inp = Path(input_path)
        out = Path(output_path)
        ws = Path(workspace_path) if workspace_path else None

        try:
            result = process_single_file(
                inp, out, workspace_path=ws, extract_segments=extract_segments, force=force, force_ocr=force_ocr
            )
            click.echo(f"변환 완료: {result['file_id']}")
            if result.get("segments_count"):
                click.echo(f"세그먼트 추출: {result['segments_count']}개")
            if result.get("registry_updated"):
                click.echo("file_registry 갱신됨")
        except Exception as e:
            click.echo(f"오류: {e}", err=True)
            sys.exit(1)

    else:
        click.echo("사용법 오류: --input 또는 --batch 중 하나를 지정해야 합니다.")
        click.echo(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
