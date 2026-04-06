#!/usr/bin/env python3.13
"""
tests/test_run_section_writer.py — WP-R3 regression tests

Tests:
1. write_single_section handles list-shaped blueprints
2. draft markdown/meta are saved without save_draft argument-order errors
3. placeholders register new draft queries with stable IDs
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import scripts.run_section_writer as section_writer


def test_write_single_section_accepts_list_blueprint_and_registers_queries(tmp_path, monkeypatch):
    workspace = tmp_path / "PRJ-2026-TST-901"
    workspace.mkdir()
    (workspace / "07_drafts").mkdir()

    draft_queries = {
        "project_id": workspace.name,
        "current_phase": "P4",
        "created_at": "2026-04-03T04:36:31Z",
        "updated_at": "2026-04-03T04:36:31Z",
        "queries": [
            {
                "query_id": "DQ-001",
                "query_type": "data_verification",
                "section_id": "SEC-3.1",
                "question": "배출량 1,250 tCO2e 수치 정확성 확인 요청",
                "priority": "high",
                "status": "open",
                "created_at": "2026-04-03T09:35:24Z",
            },
            {
                "query_id": "DQ-002",
                "query_type": "additional_data_request",
                "section_id": "SEC-3.1",
                "question": "Scope 2 에너지 관련 배출량 데이터 필요",
                "priority": "high",
                "status": "open",
                "created_at": "2026-04-03T09:35:25Z",
            },
            {
                "query_id": "DQ-003",
                "query_type": "additional_data_request",
                "section_id": "SEC-3.1",
                "question": "Scope 3 배출량 및 감축 전략 필요",
                "priority": "high",
                "status": "open",
                "created_at": "2026-04-03T09:35:26Z",
            },
        ],
    }
    (workspace / "draft_queries.json").write_text(
        json.dumps(draft_queries, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    blueprint = {
        "blueprint_version": "1.0.0",
        "project_id": workspace.name,
        "approved": True,
        "sections": [
            {
                "section_id": "SEC-3.1",
                "title": "기후변화 대응",
                "depth_level": 3,
                "writing_approach": "data_table_with_narrative",
                "expected_length_range": {"min_words": 800, "max_words": 1500},
                "required_subsections": ["SEC-3.1.1", "SEC-3.1.2"],
                "framework_disclosures": ["GRI 305-1", "GRI 305-2", "TCFD Metrics-a"],
                "writing_constraints": ["배출량 단위는 tCO2e로 통일"],
                "tone": "formal_technical",
                "flexibility_mode": "rigid",
                "model_recommendation": None,
                "required_evidence_confidence": 0.85,
                "numeric_dependency_level": "high",
                "human_approval_scope": "all",
                "disclosure_completeness_threshold": 0.9,
                "fallback_if_evidence_missing": "placeholder_with_query",
                "placeholder_policy": {
                    "marker_format": "[확인필요: {reason}]",
                    "auto_register_query": True,
                },
                "approved": False,
            }
        ],
    }
    structure_index = {
        "structure_version": "1.0.0",
        "project_id": workspace.name,
        "entries": [
            {
                "section_id": "SEC-3.1",
                "parent_section_id": "SEC-3",
                "heading_text": "기후변화 대응",
                "heading_level": 2,
                "heading_anchor": "climate-change-response",
                "toc_path": ["환경", "기후변화 대응"],
                "draft_artifact_ref": None,
                "framework_mappings": [],
            }
        ],
    }
    bucket_data = {
        "section_id": "SEC-3.1",
        "evidence_items": [
            {
                "source_segment_id": "SEG-00001",
                "content": "온실가스 배출량: 1,250 tCO2e",
            }
        ],
    }

    class FakeDispatcher:
        def dispatch(self, agent, context, output_files, section_id):
            assert agent == "section-writer"
            assert section_id == "SEC-3.1"
            assert context["blueprint"]["section_id"] == "SEC-3.1"
            assert output_files == ["07_drafts/SEC-3.1.md"]
            return SimpleNamespace(
                success=True,
                content=(
                    "---\n"
                    "draft_version: 2\n"
                    "confidence: 0.61\n"
                    "---\n"
                    "<!-- anchor:SEC-3.1 -->\n"
                    "## 기후변화 대응\n\n"
                    "온실가스 배출량은 1,250 tCO2e입니다. <!-- src:SEG-00001@v1 -->\n\n"
                    "[확인필요: Scope 3 카테고리별 배출량 데이터 필요]\n"
                ),
                error=None,
                run_id="RUN-TEST-SEC-31",
            )

    class FakeStateManager:
        def __init__(self):
            self.progress_updates = []
            self.blocking_issues = []

        def update_section_progress(self, **kwargs):
            self.progress_updates.append(kwargs)

        def add_blocking_issue(self, **kwargs):
            self.blocking_issues.append(kwargs)

    state_manager = FakeStateManager()
    monkeypatch.setattr(section_writer, "log_event", lambda **kwargs: None)

    result = section_writer.write_single_section(
        workspace=workspace,
        section_id="SEC-3.1",
        bucket_data=bucket_data,
        blueprint=blueprint,
        structure_index=structure_index,
        dispatcher=FakeDispatcher(),
        state_manager=state_manager,
    )

    assert result["success"] is True
    assert result["draft_path"] == "07_drafts/SEC-3.1.md"
    assert result["meta_path"] == "07_drafts/SEC-3.1_meta.json"
    # OD-9: new_queries contains at least 1 ID (enforcement-violation DQ)
    assert len(result["new_queries"]) >= 1
    assert result["placeholder_count"] == 1

    saved_draft = (workspace / "07_drafts" / "SEC-3.1.md").read_text(encoding="utf-8")
    assert "## 기후변화 대응" in saved_draft
    assert "[확인필요: Scope 3 카테고리별 배출량 데이터 필요]" in saved_draft
    # OD-9: body unchanged (no marker re-insertion to avoid recursion)

    saved_meta = json.loads((workspace / "07_drafts" / "SEC-3.1_meta.json").read_text(encoding="utf-8"))
    assert saved_meta["section_id"] == "SEC-3.1"
    assert saved_meta["draft_version"] == 2
    assert saved_meta["draft_confidence"] == saved_meta["confidence"]
    assert saved_meta["placeholder_count"] == 1
    assert saved_meta["source_tag_count"] == 1
    # OD-9: violation metadata present
    assert "source_tag_violation" in saved_meta
    assert saved_meta["source_tag_violation"]["untagged_paragraph_count"] >= 1

    updated_queries = json.loads((workspace / "draft_queries.json").read_text(encoding="utf-8"))
    # OD-9: enforcement adds source_tag_violation DQs (total >= 4 original + 1+ enforcement)
    assert len(updated_queries["queries"]) >= 5
    # At least one violation-type query was registered
    violation_queries = [q for q in updated_queries["queries"] if q.get("query_type") == "source_tag_violation"]
    assert len(violation_queries) >= 1

    assert state_manager.progress_updates == [
        {
            "section_id": "SEC-3.1",
            "status": "drafted",
            "draft_version": 2,
            "confidence": saved_meta["draft_confidence"],
        }
    ]
    assert state_manager.blocking_issues == []


def test_write_single_section_fallback_bucket_generates_placeholder_only(tmp_path, monkeypatch):
    """폴백 버킷 감지 시 LLM 미호출 + placeholder-only 초안 생성 검증."""
    workspace = tmp_path / "PRJ-2026-TST-902"
    workspace.mkdir()
    (workspace / "07_drafts").mkdir()

    # 빈 draft_queries (중복 방지 로직 검증용)
    (workspace / "draft_queries.json").write_text(
        json.dumps(
            {
                "project_id": workspace.name,
                "query_version": "1.0",
                "queries": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    blueprint = {
        "sections": [
            {
                "section_id": "SEC-3.2",
                "title": "폐기물 관리",
                "depth_level": 3,
                "flexibility_mode": "rigid",
                "fallback_if_evidence_missing": "placeholder_with_query",
                "placeholder_policy": {"marker_format": "[확인필요: {reason}]"},
            }
        ],
    }
    structure_index = {
        "entries": [
            {
                "section_id": "SEC-3.2",
                "heading_text": "폐기물 관리",
                "depth_level": 3,
                "framework_mappings": [],
            }
        ],
    }
    # 폴백 버킷: segments=[], status=generated_fallback
    fallback_bucket = {
        "section_id": "SEC-3.2",
        "status": "generated_fallback",
        "segments": [],
        "evidence_items": [],
        "confidence": 0.0,
    }

    class FakeDispatcher:
        dispatch_called = False

        def dispatch(self, agent, context, output_files, section_id):
            FakeDispatcher.dispatch_called = True
            raise AssertionError("LLM should NOT be called for fallback bucket")

    class FakeStateManager:
        def __init__(self):
            self.progress_updates = []
            self.blocking_issues = []

        def update_section_progress(self, **kwargs):
            self.progress_updates.append(kwargs)

        def add_blocking_issue(self, **kwargs):
            self.blocking_issues.append(kwargs)

    state_manager = FakeStateManager()
    monkeypatch.setattr(section_writer, "log_event", lambda **kwargs: None)

    result = section_writer.write_single_section(
        workspace=workspace,
        section_id="SEC-3.2",
        bucket_data=fallback_bucket,
        blueprint=blueprint,
        structure_index=structure_index,
        dispatcher=FakeDispatcher(),
        state_manager=state_manager,
    )

    # 1. 성공적으로 완료
    assert result["success"] is True
    # 2. 폴백 모드 플래그
    assert result.get("fallback_mode") is True
    # 3. LLM 미호출
    assert FakeDispatcher.dispatch_called is False
    # 4. confidence 0.0
    assert result["confidence"] == 0.0

    # 5. 초안 본문 검증
    saved_draft = (workspace / "07_drafts" / "SEC-3.2.md").read_text(encoding="utf-8")
    assert "<!-- anchor:SEC-3.2 -->" in saved_draft
    assert "### 폐기물 관리" in saved_draft
    # placeholder 포함
    assert "[확인필요:" in saved_draft
    # src: 태그 없음 (증거 없음)
    assert "<!-- src:" not in saved_draft
    # SEG-* 패턴 없음
    assert "SEG-" not in saved_draft

    # 6. 메타 검증
    saved_meta = json.loads((workspace / "07_drafts" / "SEC-3.2_meta.json").read_text(encoding="utf-8"))
    assert saved_meta["fallback_mode"] is True
    assert saved_meta["draft_confidence"] == 0.0
    assert saved_meta["source_tag_count"] == 0
    assert saved_meta["placeholder_count"] >= 1

    # 7. 상태 업데이트
    assert state_manager.progress_updates == [
        {
            "section_id": "SEC-3.2",
            "status": "drafted",
            "draft_version": 1,
            "confidence": 0.0,
        }
    ]
    assert state_manager.blocking_issues == []
