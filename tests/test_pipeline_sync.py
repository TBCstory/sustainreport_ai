"""HD-4: Pipeline status sync tests."""
import json
import tempfile
from pathlib import Path


def test_sync_workspace_creates_all_summaries():
    """sync_workspace가 3개 파생 파일을 모두 갱신해야 한다."""
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


def test_sync_workspace_returns_counts():
    """sync_workspace 반환값에 blocking_issues와 next_actions 카운트가 있어야 한다."""
    from scripts.utils import sync_workspace

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
        assert isinstance(result["blocking_issues"], int)
        assert isinstance(result["next_actions"], int)
        assert isinstance(result["project_state"], bool)