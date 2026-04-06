from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import normalize
from scripts import run_ingestion as ingestion
from scripts.init_workspace import create_workspace


def test_resolve_markitdown_command_falls_back_to_repo_venv(monkeypatch) -> None:
    monkeypatch.setattr(ingestion.sys, "executable", "/tmp/outside-venv/bin/python")
    monkeypatch.setattr(ingestion.shutil, "which", lambda _: None)

    command = ingestion.resolve_markitdown_command()

    assert command == str((ingestion.PROJECT_ROOT / ".venv" / "bin" / "markitdown").resolve())


def test_run_ingestion_uses_resolved_markitdown_and_nested_segment_counter(tmp_path: Path, monkeypatch) -> None:
    workspace = create_workspace("PRJ-2026-TST-101", tmp_path)

    top_file = workspace / "01_raw" / "top.txt"
    deep_file = workspace / "01_raw" / "nested" / "deeper" / "deep.txt"
    deep_file.parent.mkdir(parents=True, exist_ok=True)
    top_file.write_text(
        "Top-level ESG report content with enough text to create a segment.\n"
        "환경 데이터와 사회 데이터가 모두 포함되어 있습니다.\n",
        encoding="utf-8",
    )
    deep_file.write_text(
        "Nested ESG report content with enough text to create another segment.\n"
        "지배구조와 리스크 관리 내용이 포함되어 있습니다.\n",
        encoding="utf-8",
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text("", encoding="utf-8")
    fake_markitdown = fake_bin / "markitdown"
    fake_markitdown.write_text("", encoding="utf-8")
    fake_markitdown.chmod(0o755)

    invoked_commands: list[str] = []

    def fake_run(cmd: list[str], capture_output: bool = False, text: bool = False, timeout: int = 120, **kwargs):
        del capture_output, text, timeout
        invoked_commands.append(cmd[0])
        input_path = Path(cmd[1])
        output_path = Path(cmd[3])
        output_path.write_text(
            f"# {input_path.stem}\n\n{input_path.read_text(encoding='utf-8')}\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(ingestion.sys, "executable", str(fake_python))
    monkeypatch.setattr(ingestion.subprocess, "run", fake_run)
    monkeypatch.setattr(ingestion.shutil, "which", lambda _: None)
    # Also mock normalize.py subprocess so it uses the same fake markitdown path
    monkeypatch.setattr(normalize.subprocess, "run", fake_run)
    monkeypatch.setattr(normalize, "resolve_markitdown_command", lambda: str(fake_markitdown.resolve()))

    result = ingestion.run_ingestion(workspace)

    assert result["success"] is True
    assert result["files_success"] == 2
    assert result["files_failed"] == 0
    assert result["segments_created"] == 2
    assert invoked_commands == [str(fake_markitdown.resolve()), str(fake_markitdown.resolve())]

    registry = json.loads((workspace / "02_file_registry" / "file_registry.json").read_text(encoding="utf-8"))
    source_paths = sorted(entry["source_path"] for entry in registry["files"])
    assert source_paths == ["01_raw/nested/deeper/deep.txt", "01_raw/top.txt"]

    segment_ids = sorted(path.stem for path in (workspace / "04_segments").glob("SEG-*.md"))
    assert segment_ids == ["SEG-00001", "SEG-00002"]

    next_segment = json.loads((workspace / "04_segments" / "next_segment_id.json").read_text(encoding="utf-8"))
    assert next_segment["next_id"] == 3


def test_ingestion_uses_normalize_process_single_file(tmp_path, monkeypatch):
    """run_ingestion이 normalize.process_single_file을 호출하는지 확인한다."""
    from scripts import run_ingestion

    call_log = []

    def mock_process_single_file(
        input_path, output_path, workspace_path=None, extract_segments=False, force=False, force_ocr=False
    ):
        call_log.append(str(input_path))
        # 빈 md 파일 생성 (정상 변환 시뮬레이션)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "---\nfile_id: F-0001\nconversion_method: markitdown\n---\n\n테스트 내용\n", encoding="utf-8"
        )
        return {"conversion_method": "markitdown", "char_count": 10}

    monkeypatch.setattr(run_ingestion, "process_single_file", mock_process_single_file)

    # 워크스페이스 설정
    ws = tmp_path / "PRJ-TEST"
    raw_dir = ws / "01_raw"
    raw_dir.mkdir(parents=True)
    test_file = raw_dir / "test.pdf"
    test_file.write_bytes(b"%PDF-1.4 test content")

    result = run_ingestion.run_ingestion(workspace=str(ws))

    assert len(call_log) > 0, "process_single_file이 호출되지 않았습니다 (구 markitdown 직접 호출 경로 사용 중)"
    assert str(test_file) in call_log


def test_ingestion_creates_data_gap_report(tmp_path, monkeypatch):
    """run_ingestion 완료 후 data_gap_report.json이 생성되는지 확인한다."""
    from scripts import normalize as norm_module
    from scripts import run_ingestion

    def mock_process_single_file(input_path, output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("---\nfile_id: F-0001\nconversion_method: markitdown\n---\n\n내용\n", encoding="utf-8")
        return {"conversion_method": "markitdown", "char_count": 5}

    monkeypatch.setattr(norm_module, "process_single_file", mock_process_single_file)

    ws = tmp_path / "PRJ-TEST"
    (ws / "01_raw").mkdir(parents=True)
    (ws / "01_raw" / "sample.pdf").write_bytes(b"%PDF-1.4 content")

    result = run_ingestion.run_ingestion(workspace=str(ws))

    gap_report_path = ws / "02_file_registry" / "data_gap_report.json"
    assert gap_report_path.exists(), "data_gap_report.json이 생성되지 않았습니다"

    with open(gap_report_path, encoding="utf-8") as f:
        report = json.load(f)

    assert "summary" in report
    assert "conversion_method_breakdown" in report
    assert report["summary"]["total_files"] >= 1


def test_ingestion_creates_unconvertible_files(tmp_path, monkeypatch):
    """변환 실패 파일이 있을 때 unconvertible_files.json이 생성되는지 확인한다."""
    from scripts import normalize as norm_module
    from scripts import run_ingestion

    def mock_process_fail(input_path, output_path, **kwargs):
        raise RuntimeError("HWP 변환 실패: kordoc 미설치")

    monkeypatch.setattr(norm_module, "process_single_file", mock_process_fail)

    ws = tmp_path / "PRJ-TEST"
    (ws / "01_raw").mkdir(parents=True)
    (ws / "01_raw" / "report.hwp").write_bytes(b"HWP content")

    result = run_ingestion.run_ingestion(workspace=str(ws))

    unconvertible_path = ws / "02_file_registry" / "unconvertible_files.json"
    assert unconvertible_path.exists(), "unconvertible_files.json이 생성되지 않았습니다"

    with open(unconvertible_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["unconvertible_count"] >= 1
