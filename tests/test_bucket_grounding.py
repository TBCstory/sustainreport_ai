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
        seg_file.write_text(
            f"---\nsegment_id: {seg_id}\nsource_file_id: F-{i+1:04d}\nheading_path: {content.split()[0]}\n---\n\n{content}\n",
            encoding="utf-8"
        )
        segments.append({
            "segment_id": seg_id,
            "source_file_id": f"F-{i+1:04d}",
            "heading_path": content.split()[0],
            "file_path": f"04_segments/{seg_id}.md",
            "content_preview": content[:500],
        })

    (ws / "04_segments" / "segment_manifest.json").write_text(
        json.dumps({"segments": segments}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

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

        manifest = json.loads(
            (ws / "04_segments" / "segment_manifest.json").read_text(encoding="utf-8")
        )
        for seg in manifest.get("segments", []):
            assert "file_path" in seg, f"file_path missing in {seg["segment_id"]}"
            assert "content_preview" in seg, f"content_preview missing in {seg["segment_id"]}"


def test_grounded_bucket_has_nonzero_confidence():
    """segments가 매칭된 bucket은 confidence > 0이어야 한다."""
    from scripts.run_framework_mapper import _build_buckets_from_structure_index

    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace_with_segments(Path(tmp))

        # structure_index mock
        target_sections = [
            {
                "section_id": "SEC-3",
                "heading_text": "환경",
                "toc_path": ["환경", "온실가스"],
                "framework_mappings": [
                    {"framework": "GRI", "disclosure": "305-1", "coverage_type": "primary"}
                ]
            }
        ]

        segment_manifest = json.loads(
            (ws / "04_segments" / "segment_manifest.json").read_text(encoding="utf-8")
        )

        _build_buckets_from_structure_index(ws, target_sections, segment_manifest, {})

        bucket = json.loads((ws / "06_buckets" / "SEC-3.json").read_text(encoding="utf-8"))
        # matched segments가 있으면 grounded
        if bucket.get("segments"):
            assert bucket["confidence"] > 0, f"grounded bucket should have confidence > 0"
            assert bucket["bucket_status_type"] == "grounded"


def test_empty_bucket_has_zero_confidence():
    """segments가 없는 bucket은 confidence=0.0이어야 한다."""
    from scripts.run_framework_mapper import _build_buckets_from_structure_index

    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace_with_segments(Path(tmp), num_files=0)
        # 빈 워크스페이스에 segment 없이 테스트
        (ws / "04_segments" / "segment_manifest.json").write_text(
            json.dumps({"segments": []}), encoding="utf-8"
        )

        target_sections = [
            {
                "section_id": "SEC-99",
                "heading_text": "테스트",
                "toc_path": ["관련없는 키워드"],
                "framework_mappings": []
            }
        ]

        _build_buckets_from_structure_index(
            ws, target_sections, {"segments": []}, {}
        )

        bucket = json.loads((ws / "06_buckets" / "SEC-99.json").read_text(encoding="utf-8"))
        assert bucket["confidence"] == 0.0, f"empty bucket should have confidence=0.0, got {bucket["confidence"]}"
        assert bucket["bucket_status_type"] == "empty"