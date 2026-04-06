#!/usr/bin/env python3.13
"""
tests/test_run_toc_planner.py — WP-R2 regression tests

Tests:
1. planning bundle parser tolerates fenced JSON with surrounding prose
2. empty planner responses raise a clear error
3. P2 outputs are saved before approval polling starts
4. live prompt includes runtime artifact snapshots
5. parse failure leaves debuggable artifacts in workspace
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.run_toc_planner as toc_planner


def _sample_planning_bundle(project_id: str) -> dict:
    return {
        "structure_index": {
            "structure_version": "1.0.0",
            "project_id": project_id,
            "entries": [
                {
                    "section_id": "SEC-1",
                    "parent_section_id": None,
                    "heading_text": "테스트 섹션",
                    "heading_level": 1,
                    "heading_anchor": "test-section",
                    "toc_path": ["테스트 섹션"],
                    "draft_artifact_ref": None,
                    "framework_mappings": [],
                }
            ],
        },
        "writing_blueprint": {
            "blueprint_version": "1.0.0",
            "project_id": project_id,
            "approved": True,
            "approved_at": "2026-04-06T00:00:00Z",
            "sections": [
                {
                    "section_id": "SEC-1",
                    "title": "테스트 섹션",
                    "depth_level": 1,
                    "writing_approach": "narrative",
                    "expected_length_range": {"min_words": 100, "max_words": 200},
                    "required_subsections": [],
                    "framework_disclosures": [],
                    "writing_constraints": [],
                    "tone": "formal_general",
                    "flexibility_mode": "flex",
                    "model_recommendation": None,
                    "required_evidence_confidence": 0.7,
                    "numeric_dependency_level": "low",
                    "human_approval_scope": "numbers_only",
                    "disclosure_completeness_threshold": 0.8,
                    "fallback_if_evidence_missing": "low_confidence_draft",
                    "placeholder_policy": {
                        "marker_format": "[확인필요: {reason}]",
                        "auto_register_query": True,
                    },
                    "approved": False,
                }
            ],
        },
        "section_manifest": {
            "manifest_version": "1.0.0",
            "project_id": project_id,
            "sections": [
                {
                    "section_id": "SEC-1",
                    "title": "테스트 섹션",
                    "writing_mode": "flex",
                    "writer_agent": "section-writer",
                    "draft_status": "pending",
                    "draft_confidence": None,
                    "evidence_count": 1,
                    "notes": "",
                }
            ],
            "summary": {
                "total_sections": 1,
                "manual_sections": 0,
                "flex_sections": 1,
                "rigid_sections": 0,
                "total_estimated_words": 200,
                "framework_count": 0,
            },
        },
    }


def test_parse_planning_bundle_accepts_fenced_json_with_surrounding_text():
    bundle = _sample_planning_bundle("PRJ-2026-TST-900")
    raw = (
        "아래 planning bundle을 사용하세요.\n\n"
        "```json\n"
        f"{json.dumps(bundle, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "필요하면 후속 검토를 진행하세요."
    )

    parsed = toc_planner.parse_planning_bundle(raw)

    assert parsed["structure_index"]["project_id"] == "PRJ-2026-TST-900"
    assert parsed["writing_blueprint"]["sections"][0]["section_id"] == "SEC-1"
    assert parsed["section_manifest"]["summary"]["total_sections"] == 1


def test_parse_planning_bundle_empty_response_has_clear_error():
    with pytest.raises(ValueError, match="Planning bundle response was empty"):
        toc_planner.parse_planning_bundle("   \n\t  ")


def test_run_toc_planner_saves_outputs_before_waiting_for_approval(tmp_path, monkeypatch):
    workspace = tmp_path / "PRJ-2026-TST-900"
    (workspace / "04_segments").mkdir(parents=True)
    (workspace / "context_bus").mkdir()
    (workspace / "05_planning").mkdir(parents=True)
    (workspace / "04_segments" / "segment_manifest.json").write_text("{}", encoding="utf-8")

    # PKT-A003: toc_draft.json and P1.5_to_P2 gate must be approved before blueprint (P2) can run
    (workspace / "05_planning" / "toc_draft.json").write_text(
        json.dumps({"project_id": workspace.name, "status": "approved", "sections": []}), encoding="utf-8"
    )
    (workspace / "approval_gates.json").write_text(
        json.dumps({"gates": {"P1.5_to_P2": {"status": "approved"}, "P2_to_P3": {"status": "waiting"}}}),
        encoding="utf-8",
    )

    bundle = _sample_planning_bundle(workspace.name)

    class FakeStateManager:
        def __init__(self):
            self.phase_updates: list[tuple[str, str]] = []
            self.wait_calls: list[dict] = []
            self.synced = False

        def set_phase_status(self, phase: str, status: str) -> None:
            self.phase_updates.append((phase, status))

        def sync(self) -> None:
            self.synced = True

        def wait_for_approval(self, **kwargs) -> None:
            self.wait_calls.append(kwargs)

    state_manager = FakeStateManager()

    monkeypatch.setattr(
        toc_planner,
        "_build_planning_prompt",
        lambda workspace, segment_manifest_path: "test prompt",
    )
    monkeypatch.setattr(
        toc_planner,
        "_call_toc_planner",
        lambda prompt, router: {
            "content": json.dumps(bundle, ensure_ascii=False),
            "model": "fake-model",
            "run_id": "RUN-TEST-SAVE",
        },
    )
    monkeypatch.setattr(
        toc_planner,
        "_get_gate_config",
        lambda gate_name: {"required_approvers": ["project_manager", "consultant_lead"]},
    )

    result = toc_planner.run_toc_planner(
        workspace=workspace,
        state_manager=state_manager,
        skip_approval=False,
    )

    # OD-1 fix: run_toc_planner returns immediately with waiting status (no polling)
    assert result["success"] is True
    assert result["waiting"] is True
    assert result["gate_status"] == "waiting"
    assert result["gate_name"] == "P2_to_P3"
    assert result["outputs"] == [
        "05_planning/structure_index.json",
        "05_planning/writing_blueprint.json",
        "05_planning/section_manifest.json",
    ]
    assert state_manager.phase_updates == [("P2", "complete")]
    assert state_manager.synced is True
    assert state_manager.wait_calls == [
        {
            "gate_name": "P2_to_P3",
            "required_approvers": ["project_manager", "consultant_lead"],
            "requester": "run_toc_planner",
        }
    ]

    saved_blueprint = json.loads((workspace / "05_planning" / "writing_blueprint.json").read_text(encoding="utf-8"))
    assert saved_blueprint["project_id"] == workspace.name
    assert saved_blueprint["approved"] is False


def test_build_planning_prompt_includes_runtime_artifact_snapshots(tmp_path):
    workspace = tmp_path / "PRJ-2026-TST-901"
    (workspace / "02_file_registry").mkdir(parents=True)
    (workspace / "03_normalized_md").mkdir()
    (workspace / "04_segments").mkdir()
    (workspace / "guidance").mkdir()

    (workspace / "02_file_registry" / "file_registry.json").write_text(
        json.dumps({"files": [{"file_id": "F-0001"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (workspace / "04_segments" / "segment_manifest.json").write_text(
        json.dumps({"segments": [{"segment_id": "SEG-00001"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (workspace / "03_normalized_md" / "F-0001.md").write_text(
        "환경 데이터와 사회 데이터가 포함된 테스트 문서",
        encoding="utf-8",
    )
    (workspace / "guidance" / "style_guide.json").write_text(
        json.dumps({"voice_and_tone": {"formality": "formal"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (workspace / "guidance" / "terminology_dictionary.json").write_text(
        json.dumps({"core_terms": {"ESG": {"term_ko": "환경·사회·지배구조"}}}, ensure_ascii=False),
        encoding="utf-8",
    )

    prompt = toc_planner._build_planning_prompt(
        workspace=workspace,
        segment_manifest_path=workspace / "04_segments" / "segment_manifest.json",
    )

    assert str(workspace) in prompt
    assert "{workspace}" not in prompt
    assert '"project_id": "PRJ-2026-TST-901"' in prompt
    assert "환경 데이터와 사회 데이터가 포함된 테스트 문서" in prompt
    assert "_requires_input" in prompt
    assert "추가 파일 요청" in prompt


def test_run_toc_planner_saves_debug_artifacts_on_parse_failure(tmp_path, monkeypatch):
    workspace = tmp_path / "PRJ-2026-TST-902"
    (workspace / "02_file_registry").mkdir(parents=True)
    (workspace / "03_normalized_md").mkdir()
    (workspace / "04_segments").mkdir()
    (workspace / "guidance").mkdir()

    (workspace / "02_file_registry" / "file_registry.json").write_text(
        json.dumps({"files": [{"file_id": "F-0001"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (workspace / "04_segments" / "segment_manifest.json").write_text(
        json.dumps({"segments": [{"segment_id": "SEG-00001"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (workspace / "03_normalized_md" / "F-0001.md").write_text("테스트 본문", encoding="utf-8")
    (workspace / "guidance" / "style_guide.json").write_text(
        json.dumps({"voice_and_tone": {"formality": "formal"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (workspace / "guidance" / "terminology_dictionary.json").write_text(
        json.dumps({"core_terms": {"ESG": {"term_ko": "환경·사회·지배구조"}}}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        toc_planner,
        "_call_toc_planner",
        lambda prompt, router: {
            "content": "Planner could not comply with the contract.",
            "model": "fake-model",
            "run_id": "RUN-TEST-PLAN",
        },
    )

    result = toc_planner.run_toc_planner(workspace=workspace, skip_approval=True)

    assert result["success"] is False
    assert "Debug artifacts saved" in result["message"]
    assert result["outputs"] == [
        "05_planning/_debug/toc_planner_prompt.txt",
        "05_planning/_debug/toc_planner_raw_response.txt",
        "05_planning/_debug/toc_planner_failure.json",
    ]

    raw_path = workspace / "05_planning" / "_debug" / "toc_planner_raw_response.txt"
    failure_path = workspace / "05_planning" / "_debug" / "toc_planner_failure.json"
    assert raw_path.read_text(encoding="utf-8") == "Planner could not comply with the contract."

    failure_payload = json.loads(failure_path.read_text(encoding="utf-8"))
    assert failure_payload["failure_stage"] == "parse"
    assert failure_payload["model"] == "fake-model"
    assert failure_payload["run_id"] == "RUN-TEST-PLAN"


def test_toc_draft_mode_creates_toc_draft_json(tmp_path, monkeypatch):
    """--toc-draft 모드 실행 시 05_planning/toc_draft.json이 생성되는지 확인."""
    ws = tmp_path / "PRJ-TEST"
    (ws / "04_segments").mkdir(parents=True)
    (ws / "00_definition").mkdir(parents=True)
    (ws / "04_segments" / "segment_manifest.json").write_text(json.dumps({"segments": []}), encoding="utf-8")

    def mock_llm_call(*args, **kwargs):
        return {
            "content": json.dumps(
                {
                    "sections": [
                        {
                            "section_id": "SEC-1",
                            "heading_text": "CEO 메시지",
                            "level": 1,
                            "parent_section_id": None,
                            "estimated_pages": 2,
                            "frameworks": [],
                            "notes": None,
                        },
                        {
                            "section_id": "SEC-2",
                            "heading_text": "지배구조",
                            "level": 1,
                            "parent_section_id": None,
                            "estimated_pages": 5,
                            "frameworks": ["GRI 2-9"],
                            "notes": None,
                        },
                    ]
                }
            ),
            "run_id": "test-run-001",
        }

    monkeypatch.setattr(
        toc_planner.ModelRouter, "complete_messages", lambda self, messages, agent, **kwargs: mock_llm_call()
    )

    result = toc_planner.run_toc_draft(workspace=str(ws), skip_approval=True)

    assert result["success"] is True
    toc_draft_path = ws / "05_planning" / "toc_draft.json"
    assert toc_draft_path.exists(), "toc_draft.json이 생성되지 않았습니다"

    with open(toc_draft_path, encoding="utf-8") as f:
        toc = json.load(f)

    assert len(toc["sections"]) == 2
    assert toc["status"] == "approved"  # skip_approval=True이므로


def test_blueprint_blocked_without_toc_approval(tmp_path):
    """toc_draft.json 없이 run_toc_planner 기본 모드 실행 시 실패 반환 확인."""
    ws = tmp_path / "PRJ-TEST"
    (ws / "04_segments").mkdir(parents=True)
    (ws / "04_segments" / "segment_manifest.json").write_text(json.dumps({"segments": []}), encoding="utf-8")

    # toc_draft.json 없는 상태에서 기본 모드 실행
    result = toc_planner.run_toc_planner(workspace=str(ws), skip_approval=False)

    assert result["success"] is False
    assert "toc_draft" in result["message"].lower() or "P1.5" in result["message"]


def test_blueprint_proceeds_after_toc_approval(tmp_path, monkeypatch):
    """toc_draft.json이 존재하고 gate가 approved이면 blueprint 생성이 진행됨."""
    ws = tmp_path / "PRJ-TEST"
    (ws / "04_segments").mkdir(parents=True)
    (ws / "05_planning").mkdir(parents=True)
    (ws / "00_definition").mkdir(parents=True)
    (ws / "04_segments" / "segment_manifest.json").write_text(json.dumps({"segments": []}), encoding="utf-8")

    # toc_draft.json 미리 생성 (approved 상태)
    (ws / "05_planning" / "toc_draft.json").write_text(
        json.dumps({"project_id": "PRJ-TEST", "status": "approved", "sections": []}), encoding="utf-8"
    )

    # approval_gates.json에 P1.5_to_P2 approved 기록
    (ws / "approval_gates.json").write_text(
        json.dumps({"gates": {"P1.5_to_P2": {"status": "approved"}}}), encoding="utf-8"
    )

    bundle = _sample_planning_bundle(ws.name)

    monkeypatch.setattr(
        toc_planner,
        "_build_planning_prompt",
        lambda workspace, segment_manifest_path: "test prompt",
    )
    monkeypatch.setattr(
        toc_planner,
        "_call_toc_planner",
        lambda prompt, router: {
            "content": json.dumps(bundle, ensure_ascii=False),
            "model": "fake-model",
            "run_id": "test-run-002",
        },
    )
    monkeypatch.setattr(
        toc_planner,
        "_get_gate_config",
        lambda gate_name: {"required_approvers": ["project_manager", "consultant_lead"]},
    )

    result = toc_planner.run_toc_planner(workspace=str(ws), skip_approval=True)

    # 성공하거나 최소한 "toc_draft 미승인" 오류는 발생하지 않아야 함
    assert "toc_draft" not in result.get("message", "").lower() or result["success"] is True


def test_build_toc_draft_prompt_uses_intake_manifest_canonical_keys(tmp_path):
    """PKT-B003: custom_toc_reference와 section_priority가 LLM 프롬프트에 반영됨을 검증."""
    segment_manifest = {"segments": [{"segment_id": "SEG-00001", "heading_path": "환경 경영"}]}
    intake_manifest = {
        "A_structure": {
            "toc_style": "framework",
            # PKT-B003: 정규 키 사용
            "custom_toc_reference": "GRI Standards 목차",
            "section_priority": ["SEC-3", "SEC-4"],
            "scope_inclusions": ["안전보건"],
            "scope_exclusions": ["정보보안"],
        }
    }

    prompt = toc_planner._build_toc_draft_prompt(segment_manifest, intake_manifest)

    # 정규 키의 값이 프롬프트에 포함되어야 함
    assert "GRI Standards 목차" in prompt
    assert "SEC-3" in prompt
    assert "SEC-4" in prompt
    # alias 키는 사용하지 않음 (정규 키가 있으므로 fallback 불필요)
    assert "preferred_toc_reference" not in prompt
    assert "priority_sections" not in prompt


def test_build_toc_draft_prompt_falls_back_to_alias_keys(tmp_path):
    """PKT-B003: 구 intake_manifest 파일의 alias 키도 정상 동작해야 함."""
    segment_manifest = {"segments": [{"segment_id": "SEG-00001", "heading_path": "환경 경영"}]}
    # 구 intake_manifest: alias 키만 사용
    intake_manifest = {
        "A_structure": {
            "toc_style": "framework",
            "preferred_toc_reference": "TCFD 구조",
            "priority_sections": ["SEC-2", "SEC-5"],
            "scope_inclusions": [],
            "scope_exclusions": [],
        }
    }

    prompt = toc_planner._build_toc_draft_prompt(segment_manifest, intake_manifest)

    # alias 키의 값이 여전히 프롬프트에 포함되어야 함
    assert "TCFD 구조" in prompt
    assert "SEC-2" in prompt
    assert "SEC-5" in prompt
