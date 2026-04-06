#!/usr/bin/env python3.13
"""
run_ingestion.py — P1 자료 투입 스크립트

역할:
1. 01_raw/ 파일을 정규화 Markdown으로 변환 (markitdown)
2. 세그먼트 추출
3. file_registry.json 갱신
4. segment_manifest.json 갱신

사용법:
    from scripts.run_ingestion import run_ingestion
    result = run_ingestion(
        workspace="/path/to/PRJ-YYYY-CODE-NNN",
        file_paths=["01_raw/환경안전보고서_2024.pdf", ...],
    )
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import hashlib

from scripts.dispatch_agent import AgentDispatcher
from scripts.normalize import process_single_file
from scripts.state_manager import StateManager

# ─────────────────────────────────────────────────────────────────────────────
# 경로 상수
# ─────────────────────────────────────────────────────────────────────────────

NORMALIZED_DIR = "03_normalized_md"
SEGMENTS_DIR = "04_segments"
FILE_REGISTRY = "02_file_registry/file_registry.json"
SEGMENT_MANIFEST = "04_segments/segment_manifest.json"
NEXT_SEGMENT_ID_FILE = "04_segments/next_segment_id.json"

# ─────────────────────────────────────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────────────────────────────────────


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────────────────────────
# HD-1: Content hash deduplication
# ─────────────────────────────────────────────────────────────────────────────


def _compute_content_hash(file_path: Path) -> str:
    """파일의 SHA-256 content hash를 계산한다."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _find_existing_file_by_hash(registry_data: dict, content_hash: str) -> Optional[str]:
    """registry에서 동일 content_hash를 가진 기존 F-ID를 찾는다.
    없으면 None 반환."""
    for entry in registry_data.get("files", []):
        if entry.get("content_hash") == content_hash:
            return entry.get("file_id")
    return None


def get_file_type(path: Path) -> str:
    """파일 확장자로 type 결정."""
    ext = path.suffix.lower()
    type_map = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".hwp": "hwp",
        ".txt": "txt",
        ".md": "markdown",
        ".xlsx": "xlsx",
        ".csv": "csv",
        ".html": "html",
    }
    return type_map.get(ext, "unknown")


def get_next_file_id(registry_path: Path) -> int:
    """기존 file_registry에서 다음 F-NNNN ID 번호 결정."""
    if not registry_path.exists():
        return 1
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        max_id = 0
        for entry in data.get("files", []):
            try:
                num = int(entry.get("file_id", "F-0000").replace("F-", ""), 10)
                if num > max_id:
                    max_id = num
            except ValueError:
                continue
        return max_id + 1
    except (json.JSONDecodeError, OSError):
        return 1


def _load_next_segment_id(workspace: Path) -> int:
    """Load the next segment ID counter from workspace."""
    counter_path = workspace / NEXT_SEGMENT_ID_FILE
    if counter_path.exists():
        try:
            data = json.loads(counter_path.read_text(encoding="utf-8"))
            return data.get("next_id", 1)
        except (json.JSONDecodeError, OSError):
            return 1
    return 1


def _save_next_segment_id(workspace: Path, next_id: int) -> None:
    """Save the next segment ID counter to workspace."""
    counter_path = workspace / NEXT_SEGMENT_ID_FILE
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    counter_path.write_text(
        json.dumps({"next_id": next_id}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _extract_body_from_segment(seg_path: Path) -> str:
    """세그먼트 파일에서 YAML front matter를 제외한 본문을 추출한다."""
    text = seg_path.read_text(encoding="utf-8")
    # --- front matter --- 패턴 제거
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3 :].strip()
    return text.strip()


def get_file_type(path: Path) -> str:
    """파일 확장자로 type 결정."""
    ext = path.suffix.lower()
    type_map = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".hwp": "hwp",
        ".txt": "txt",
        ".md": "markdown",
        ".xlsx": "xlsx",
        ".csv": "csv",
        ".html": "html",
    }
    return type_map.get(ext, "unknown")


def resolve_markitdown_command() -> Optional[str]:
    """Resolve markitdown without relying on the ambient PATH alone."""
    executable_name = "markitdown.exe" if sys.platform == "win32" else "markitdown"
    candidates = [
        Path(sys.executable).resolve().parent / executable_name,
        PROJECT_ROOT / ".venv" / "bin" / executable_name,
        PROJECT_ROOT / ".venv" / "Scripts" / executable_name,
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


def run_markitdown(
    input_path: Path,
    output_path: Path,
) -> tuple[bool, Optional[str]]:
    """
    markitdown으로 파일을 Markdown으로 변환.

    Returns:
        (success, error_message)
    """
    command = resolve_markitdown_command()
    if not command:
        return False, "markitdown command not found"

    try:
        result = subprocess.run(
            [command, str(input_path), "-o", str(output_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return True, None
        else:
            return False, result.stderr or f"markitdown failed: {result.returncode}"
    except FileNotFoundError:
        return False, "markitdown command not found"
    except subprocess.TimeoutExpired:
        return False, "markitdown timed out (>120s)"
    except Exception as e:
        return False, str(e)


def split_segments(
    normalized_md_path: Path,
    segments_dir: Path,
    file_id: str,
    workspace: Path,
    start_segment_num: int = 1,
) -> tuple[list[dict], int]:
    """
    정규화 Markdown 파일을 세그먼트 단위로 분리.

    분리 규칙:
    - H1 (`# `) 단위 또는 `---` 수평선 단위로 분리
    - 각 세그먼트는 SEG-NNNNN.md로 저장
    - heading_path는 세그먼트 첫 번째 heading 텍스트

    Args:
        normalized_md_path: 정규화된 Markdown 파일 경로
        segments_dir: 세그먼트 저장 디렉토리
        file_id: 소스 파일 ID
        workspace: 워크스페이스 경로
        start_segment_num: 시작 세그먼트 번호 (workspace-level counter)

    Returns:
        tuple of (list of segment metadata dicts, next_segment_num)
    """
    content = normalized_md_path.read_text(encoding="utf-8")

    segments = []
    segment_counter = start_segment_num

    # H1 단위 분리
    import re

    h1_pattern = re.compile(r"^# (.+)$", re.MULTILINE)
    positions = [0]
    for match in h1_pattern.finditer(content):
        positions.append(match.start())

    # 마지막 위치 추가
    positions.append(len(content))

    for i in range(len(positions) - 1):
        start = positions[i]
        end = positions[i + 1]
        segment_content = content[start:end].strip()

        if len(segment_content) < 50:  # 빈 세그먼트 건너뛰기
            continue

        # heading_path 추출
        h1_match = re.match(r"^# (.+)$", segment_content, re.MULTILINE)
        heading_path = h1_match.group(1).strip() if h1_match else f"Section {segment_counter}"

        # 세그먼트 ID
        seg_num = segment_counter
        segment_id = f"SEG-{seg_num:05d}"
        segment_filename = f"{segment_id}.md"
        segment_path = segments_dir / segment_filename

        # front matter 생성
        front_matter = f"""---
segment_id: {segment_id}
source_file_id: {file_id}
heading_path: "{heading_path}"
created_at: {utc_now()}
---
"""
        full_content = front_matter + segment_content
        segment_path.write_text(full_content, encoding="utf-8")

        segments.append(
            {
                "segment_id": segment_id,
                "source_file_id": file_id,
                "heading_path": heading_path,
                "file_path": str(segment_path.relative_to(workspace)),
                "word_count": len(segment_content.split()),
                "char_count": len(segment_content),
            }
        )

        segment_counter += 1

    return segments, segment_counter


# ─────────────────────────────────────────────────────────────────────────────
# 메인 함수
# ─────────────────────────────────────────────────────────────────────────────


def run_ingestion(
    workspace: str | Path,
    file_paths: Optional[list[str]] = None,
    state_manager: Optional[StateManager] = None,
) -> dict:
    """
    P1 자료 투입을 실행한다.

    Args:
        workspace: 워크스페이스 경로
        file_paths: 변환할 파일 경로 리스트. None이면 01_raw/에서 자동 수집.
        state_manager: StateManager 인스턴스 (선택)

    Returns:
        dict: {
            "success": bool,
            "files_processed": int,
            "files_success": int,
            "files_failed": int,
            "segments_created": int,
            "outputs": list[str],
            "errors": list[str],
        }
    """
    workspace = Path(workspace)
    raw_dir = workspace / "01_raw"
    normalized_dir = workspace / NORMALIZED_DIR
    segments_dir = workspace / SEGMENTS_DIR
    registry_path = workspace / FILE_REGISTRY
    manifest_path = workspace / SEGMENT_MANIFEST

    # 디렉토리 생성
    normalized_dir.mkdir(parents=True, exist_ok=True)
    segments_dir.mkdir(parents=True, exist_ok=True)
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    # StateManager
    if state_manager is None:
        state_manager = StateManager(workspace)

    # 파일 목록 수집
    if file_paths is None:
        extensions = (".pdf", ".docx", ".hwp", ".txt", ".md", ".xlsx", ".csv", ".html")
        file_paths = []
        for ext in extensions:
            for f in raw_dir.rglob(f"*{ext}"):
                file_paths.append(str(f))

    # 기존 file_registry 로드
    if registry_path.exists():
        try:
            registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            registry_data = {"files": []}
    else:
        registry_data = {"files": []}

    # 다음 파일 ID
    next_file_num = get_next_file_id(registry_path)

    # 결과 추적
    files_success = 0
    files_failed = 0
    segments_created = 0
    outputs = []
    errors = []
    skipped_files = []

    # Workspace-level segment counter 로드
    current_segment_num = _load_next_segment_id(workspace)

    for file_path_str in file_paths:
        file_path = Path(file_path_str)
        if not file_path.exists():
            errors.append(f"File not found: {file_path}")
            files_failed += 1
            continue

        # ─── HD-1: content hash 기반 중복 체크 ───
        content_hash = _compute_content_hash(file_path)
        existing_fid = _find_existing_file_by_hash(registry_data, content_hash)
        if existing_fid is not None:
            skipped_files.append(
                {
                    "path": str(file_path.relative_to(workspace)),
                    "existing_file_id": existing_fid,
                    "reason": "content_hash_duplicate",
                }
            )
            continue

        # 파일 ID
        file_id = f"F-{next_file_num:04d}"
        next_file_num += 1

        # 정규화 Markdown 경로
        normalized_name = f"{file_id}.md"
        normalized_path = normalized_dir / normalized_name

        # normalize.py를 통한 자동 라우팅 변환 (HWP/OCR/markitdown 자동 선택)
        conversion_method = "unknown"
        convert_success = False
        convert_error = None

        try:
            norm_result = process_single_file(
                input_path=file_path,
                output_path=normalized_path,
                workspace_path=None,  # registry는 run_ingestion에서 직접 관리
                extract_segments=False,  # 세그먼트 추출은 아래에서 별도 처리
                force=True,  # 이미 존재해도 덮어쓰기
                force_ocr=False,  # 스캔 감지는 자동 (필요 시 CLI로 --force-ocr 가능)
            )
            # process_single_file이 쓴 YAML 헤더에서 conversion_method 추출
            if normalized_path.exists():
                first_lines = normalized_path.read_text(encoding="utf-8").split("\n")[:20]
                for line in first_lines:
                    if line.startswith("conversion_method:"):
                        conversion_method = line.split(":", 1)[1].strip()
                        break
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
                        "conversion_method": conversion_method,
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
                        "conversion_method": conversion_method,
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

    # Save updated segment counter
    _save_next_segment_id(workspace, current_segment_num)

    # file_registry 저장
    registry_path.write_text(
        json.dumps(registry_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    outputs.append(str(registry_path.relative_to(workspace)))

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
        )
        + "\n",
        encoding="utf-8",
    )
    outputs.append(str(unconvertible_path.relative_to(workspace)))

    # segment_manifest.json 생성
    all_segments = []
    for seg_file in sorted(segments_dir.glob("SEG-*.md")):
        try:
            # YAML front matter 파싱: ---로囲まれた部分ach抽出
            seg_content = seg_file.read_text(encoding="utf-8")
            fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", seg_content, re.DOTALL)
            if fm_match:
                fm_lines = fm_match.group(1).split("\n")
                seg_data = {}
                for line in fm_lines:
                    if ": " in line:
                        key, val = line.split(": ", 1)
                        seg_data[key.strip()] = val.strip().strip('"')
                # HD-2: file_path와 content_preview 추가
                seg_data["file_path"] = str(seg_file.relative_to(workspace))
                seg_data["content_preview"] = _extract_body_from_segment(seg_file)[:500]
                all_segments.append(seg_data)
            else:
                raise ValueError("No front matter found")
        except Exception:
            # front matter 파싱 실패 시 기본 정보
            all_segments.append(
                {
                    "segment_id": seg_file.stem,
                    "source_file_id": None,
                    "heading_path": None,
                    "file_path": str(seg_file.relative_to(workspace)),
                    "content_preview": _extract_body_from_segment(seg_file)[:500],
                }
            )

    manifest_data = {
        "total_segments": len(all_segments),
        "segments_processed": len([s for s in all_segments if s.get("source_file_id")]),
        "segments": all_segments,
        "generated_at": utc_now(),
    }
    manifest_path.write_text(
        json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    outputs.append(str(manifest_path.relative_to(workspace)))

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
            if failed_files
            else "모든 파일이 정상 변환됐습니다.",
        ],
    }

    gap_report_path = workspace / "02_file_registry" / "data_gap_report.json"
    gap_report_path.write_text(
        json.dumps(data_gap_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    outputs.append(str(gap_report_path.relative_to(workspace)))

    # 상태 갱신
    state_manager.set_phase_status("P1", "complete")
    state_manager.sync()

    return {
        "success": files_failed == 0,
        "files_processed": files_success + files_failed,
        "files_success": files_success,
        "files_failed": files_failed,
        "segments_created": segments_created,
        "outputs": outputs,
        "errors": errors,
        "skipped_files": skipped_files,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI 진입점
# ─────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="P1 자료 투입 스크립트")
    parser.add_argument("workspace", help="워크스페이스 경로")
    parser.add_argument("--files", "-f", nargs="*", help="변환할 파일 목록")
    args = parser.parse_args()

    result = run_ingestion(
        workspace=args.workspace,
        file_paths=args.files,
    )

    print(f"\n=== P1 Ingestion Result ===")
    print(f"Files processed : {result['files_processed']}")
    print(f"  Success       : {result['files_success']}")
    print(f"  Failed         : {result['files_failed']}")
    print(f"Segments created : {result['segments_created']}")
    print(f"Outputs         : {result['outputs']}")
    if result["errors"]:
        print(f"Errors          :")
        for err in result["errors"]:
            print(f"  - {err}")

    sys.exit(0 if result["success"] else 1)
