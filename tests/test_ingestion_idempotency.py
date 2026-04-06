"""HD-1: Ingestion idempotency - 같은 파일 2회 투입 시 F/SEG 중복 방지."""
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
        reg1 = json.loads(
            (ws / "02_file_registry" / "file_registry.json").read_text(encoding="utf-8")
        )
        f_count_1 = len(reg1.get("files", []))

        # segment manifest 확인
        seg1 = json.loads(
            (ws / "04_segments" / "segment_manifest.json").read_text(encoding="utf-8")
        )
        seg_count_1 = len(seg1.get("segments", []))

        # 2회차 투입 (같은 파일)
        r2 = run_ingestion(ws, [str(test_file)])
        assert r2["success"] is True
        assert len(r2.get("skipped_files", [])) >= 1

        # registry에 F-ID 중복 없음
        reg2 = json.loads(
            (ws / "02_file_registry" / "file_registry.json").read_text(encoding="utf-8")
        )
        f_count_2 = len(reg2.get("files", []))
        assert f_count_2 == f_count_1, f"F-ID duplicated: {f_count_1} -> {f_count_2}"

        # segment manifest에 SEG 중복 없음
        seg2 = json.loads(
            (ws / "04_segments" / "segment_manifest.json").read_text(encoding="utf-8")
        )
        seg_count_2 = len(seg2.get("segments", []))
        assert seg_count_2 == seg_count_1, f"SEG duplicated: {seg_count_1} -> {seg_count_2}"


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

        reg = json.loads(
            (ws / "02_file_registry" / "file_registry.json").read_text(encoding="utf-8")
        )
        assert len(reg.get("files", [])) >= 2


def test_content_hash_stored_in_registry():
    """file_registry 엔트리에 content_hash 필드가 있어야 한다."""
    from scripts.run_ingestion import run_ingestion

    with tempfile.TemporaryDirectory() as tmp:
        ws = _make_workspace(Path(tmp))

        f = ws / "01_raw" / "test.txt"
        f.write_text("# Test\nHello.", encoding="utf-8")

        run_ingestion(ws, [str(f)])

        reg = json.loads(
            (ws / "02_file_registry" / "file_registry.json").read_text(encoding="utf-8")
        )
        entry = reg["files"][0]
        assert "content_hash" in entry
        assert entry["content_hash"].startswith("sha256:")