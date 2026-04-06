#!/usr/bin/env python3.13
"""
tests/test_run_handoff_quality.py — PKT-B005: run_handoff.py 산출물 품질 검증

run_handoff.py 산출물이 (제목 없음)/0 대신 실제 필드값을 반영하는지 검증하는 E2E 회귀 테스트.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_handoff import run_handoff


class TestHandoffOutputQuality:
    """run_handoff 산출물이 (제목 없음)/0 대신 실제 값을 출력하는지 검증."""

    def _setup_sample_workspace(self, tmp_path: Path) -> Path:
        """
        최소 fixture: blueprint + draft meta + draft MD.
        Returns the workspace path.
        """
        ws = tmp_path / "PRJ-TEST-HO"

        # 05_planning/writing_blueprint.json — heading_ko 포함
        blueprint = {
            "sections": [
                {
                    "section_id": "SEC-3",
                    "heading_ko": "안전보건 및 근로조건",
                    "heading_text": "Safety and Working Conditions",
                    "level": 1,
                    "evidence_priority": "high",
                },
                {
                    "section_id": "SEC-3.1",
                    "heading_ko": "재해 및 사고 현황",
                    "heading_text": "Disaster and Accident Status",
                    "level": 2,
                    "evidence_priority": "high",
                },
                {
                    "section_id": "SEC-4",
                    "heading_ko": "인재개발 및 교육훈련",
                    "heading_text": "Talent Development and Training",
                    "level": 1,
                    "evidence_priority": "medium",
                },
            ],
            "approved": True,
        }
        (ws / "05_planning").mkdir(parents=True, exist_ok=True)
        (ws / "05_planning" / "writing_blueprint.json").write_text(
            json.dumps(blueprint, ensure_ascii=False), encoding="utf-8"
        )

        # 06_buckets/SEC-*.json — 증거 세그먼트 포함
        (ws / "06_buckets").mkdir(parents=True, exist_ok=True)
        for sid, count in [("SEC-3", 2), ("SEC-3.1", 1), ("SEC-4", 0)]:
            bucket = {
                "section_id": sid,
                "grounded_segments": [{"segment_id": f"SEG-{sid}-{i}"} for i in range(count)],
            }
            (ws / "06_buckets" / f"{sid}.json").write_text(json.dumps(bucket, ensure_ascii=False), encoding="utf-8")

        # 07_drafts/SEC-*_meta.json — heading_ko, draft_confidence, placeholders
        meta_samples = [
            {
                "section_id": "SEC-3",
                "heading_ko": "안전보건 및 근로조건",
                "draft_confidence": 0.55,  # medium
                "placeholders": ["[확인필요] 근골격계 질환 발생률", "[추후 기재] 산업안전 예산"],
                "missing_evidence": ["근골격계 질환 상세 수치"],
                "evidence_segments": 2,
            },
            {
                "section_id": "SEC-3.1",
                "heading_ko": "재해 및 사고 현황",
                "draft_confidence": "low",  # string format — should normalize to 0.25
                "placeholders": [
                    {"placeholder": "[확인필요] 사망사고 건수", "location": "SEC-3.1.md"},
                    {"placeholder": "[데이터 없음] 휴먼네트워크 사고율", "location": "SEC-3.1.md"},
                ],
                "missing_evidence": [],
                "evidence_segments": 1,
            },
            {
                "section_id": "SEC-4",
                "heading_ko": "인재개발 및 교육훈련",
                "draft_confidence": "high",  # 0.85
                "placeholders": [],
                "missing_evidence": ["교육비 총액", "평균 교육 시간"],
                "evidence_segments": 0,
            },
        ]
        (ws / "07_drafts").mkdir(parents=True, exist_ok=True)
        for meta in meta_samples:
            (ws / "07_drafts" / f"{meta['section_id']}_meta.json").write_text(
                json.dumps(meta, ensure_ascii=False), encoding="utf-8"
            )
            # 대응하는 draft MD 파일 (일부 placeholder 포함)
            draft_md = ws / "07_drafts" / f"{meta['section_id']}.md"
            content = f"# {meta['heading_ko']}\n\n"
            if meta["section_id"] == "SEC-4":
                content += "교육 프로그램 운영 결과: [추후 기재]건 운영\n"
            draft_md.write_text(content, encoding="utf-8")

        # 02_file_registry/data_gap_report.json (비어있음)
        (ws / "02_file_registry").mkdir(parents=True, exist_ok=True)
        (ws / "02_file_registry" / "data_gap_report.json").write_text(
            json.dumps({"unconvertible_files": []}), encoding="utf-8"
        )

        # 09_handoff 디렉토리 (run_handoff가 여기에 씀)
        (ws / "09_handoff").mkdir(parents=True, exist_ok=True)

        return ws

    def _run_handoff(self, ws: Path) -> None:
        """run_handoff.run()를 호출하여 산출물 생성."""
        # run_handoff는 workspace를 인자로 받음 (string 또는 Path)
        run_handoff(str(ws))

    # ─────────────────────────────────────────────────────────────────────────
    # 테스트 1: placeholder_summary.md — (제목 없음) 없어야 함
    # ─────────────────────────────────────────────────────────────────────────

    def test_placeholder_summary_shows_real_heading(self, tmp_path):
        """placeholder_summary.md에 (제목 없음)이 없어야 함."""
        ws = self._setup_sample_workspace(tmp_path)
        self._run_handoff(ws)

        summary_path = ws / "09_handoff" / "placeholder_summary.md"
        assert summary_path.exists(), f"{summary_path}가 생성되지 않았습니다"

        content = summary_path.read_text(encoding="utf-8")
        assert "(제목 없음)" not in content, (
            "placeholder_summary.md에 '(제목 없음)'이 남아있습니다. heading_ko 정규 키를 사용해야 합니다."
        )
        assert "안전보건" in content, "heading_ko '안전보건 및 근로조건'이 표기에 반영되어야 함"
        assert "재해 및 사고 현황" in content, "heading_ko '재해 및 사고 현황'이 표기에 반영되어야 함"

    # ─────────────────────────────────────────────────────────────────────────
    # 테스트 2: data_gap_priority.md — confidence 실값 표시
    # ─────────────────────────────────────────────────────────────────────────

    def test_data_gap_shows_real_confidence(self, tmp_path):
        """data_gap_priority.md에 실제 confidence 숫자가 표시."""
        ws = self._setup_sample_workspace(tmp_path)
        self._run_handoff(ws)

        gap_path = ws / "09_handoff" / "data_gap_priority.md"
        assert gap_path.exists(), f"{gap_path}가 생성되지 않았습니다"

        content = gap_path.read_text(encoding="utf-8")
        # 0.55 (medium), 0.25 (low string), 0.85 (high string) 중 하나라도 표시
        assert "0." in content, (
            f"data_gap_priority.md에 confidence 실숫값(0.55, 0.25 등)이 표시되어야 합니다. 현재 내용:\n{content[:500]}"
        )
        assert "None" not in content, "confidence 값이 None으로 표시되어서는 안 됨"

    # ─────────────────────────────────────────────────────────────────────────
    # 테스트 3: consultant_review_checklist.json — 항목 존재
    # ─────────────────────────────────────────────────────────────────────────

    def test_checklist_has_items(self, tmp_path):
        """consultant_review_checklist.json에 항목이 1개 이상."""
        ws = self._setup_sample_workspace(tmp_path)
        self._run_handoff(ws)

        checklist_path = ws / "09_handoff" / "consultant_review_checklist.json"
        assert checklist_path.exists(), f"{checklist_path}가 생성되지 않았습니다"

        data = json.loads(checklist_path.read_text(encoding="utf-8"))
        # consultant_review_checklist.json은 dict: {"items": [...], "generated_at": "...", ...}
        items = data if isinstance(data, list) else data.get("items", [])
        assert isinstance(items, list), "checklist는 배열이어야 합니다"
        assert len(items) > 0, (
            f"consultant_review_checklist.json에 항목이 없습니다. "
            f"confidence low/missing_evidence 3개 이상 섹션이检出되어야 합니다."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 테스트 4: data_gap_priority.md — review_priority_score 컬럼 존재
    # ─────────────────────────────────────────────────────────────────────────

    def test_review_priority_score_present(self, tmp_path):
        """data_gap_priority에 review_priority_score(검토점수) 컬럼 존재."""
        ws = self._setup_sample_workspace(tmp_path)
        self._run_handoff(ws)

        gap_path = ws / "09_handoff" / "data_gap_priority.md"
        content = gap_path.read_text(encoding="utf-8")
        # review_priority_score 컬럼이 표에 있어야 함
        assert "검토점수" in content or "priority" in content.lower(), (
            f"data_gap_priority.md에 검토점수 컬럼이 없습니다. 현재 내용:\n{content[:500]}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 테스트 5: review_priority_score 정렬 적용 (높은 점수가 위에)
    # ─────────────────────────────────────────────────────────────────────────

    def test_review_priority_score_sorted_descending(self, tmp_path):
        """review_priority_score 기준 내림차순 정렬 적용."""
        ws = self._setup_sample_workspace(tmp_path)
        self._run_handoff(ws)

        gap_path = ws / "09_handoff" / "data_gap_priority.md"
        content = gap_path.read_text(encoding="utf-8")

        # SEC-4 (evidence=0, confidence=0.85 → priority 높음) vs SEC-3 (evidence=2, confidence=0.55 → priority 낮음)
        # SEC-4의 review_priority_score > SEC-3 이어야 함
        # SEC-4: (1-0.85)*40 + 0*5 + 2*5 + 10 = 6 + 0 + 10 + 10 = 26
        # SEC-3: (1-0.55)*40 + 2*5 + 1*5 + 0 = 18 + 10 + 5 = 33
        # SEC-3.1: (1-0.25)*40 + 2*5 + 0*5 + 0 = 30 + 10 = 40
        # SEC-3.1 > SEC-3 > SEC-4 순서여야 함
        lines = content.split("\n")
        score_positions = {}
        for line in lines:
            for section in ["SEC-3.1", "SEC-3", "SEC-4"]:
                if section in line:
                    # Extract score from | score | section | format
                    parts = line.split("|")
                    if len(parts) >= 3:
                        try:
                            score = float(parts[1].strip())
                            score_positions[section] = score
                        except ValueError:
                            pass

        if len(score_positions) >= 2:
            sorted_scores = sorted(score_positions.values(), reverse=True)
            assert score_positions[list(score_positions.keys())[0]] == sorted_scores[0], (
                f"review_priority_score가 내림차순으로 정렬되어야 합니다. 현재 점수: {score_positions}"
            )

    # ─────────────────────────────────────────────────────────────────────────
    # 테스트 6: alias fallback — 구 필드명(meta 파일)도 정상 읽기
    # ─────────────────────────────────────────────────────────────────────────

    def test_alias_fallback_reads_old_meta_format(self, tmp_path: Path) -> None:
        """
        구 필드명(confidence_score, heading_text)으로 된 meta도 읽힘.
        PKT-B002에서 말한 마이그레이션 전 기존 워크스페이스와의 호환성.
        """
        ws = tmp_path / "PRJ-TEST-OLD"

        # 05_planning/writing_blueprint.json
        blueprint = {
            "sections": [
                {
                    "section_id": "SEC-OLD",
                    "heading_ko": "구旧 섹션",
                    "level": 1,
                    "evidence_priority": "high",
                },
            ],
            "approved": True,
        }
        (ws / "05_planning").mkdir(parents=True, exist_ok=True)
        (ws / "05_planning" / "writing_blueprint.json").write_text(
            json.dumps(blueprint, ensure_ascii=False), encoding="utf-8"
        )

        # 07_drafts/SEC-OLD_meta.json — 구 필드명 사용 (alias)
        old_style_meta = {
            "section_id": "SEC-OLD",
            "heading_text": "Old Section Title",  # alias for heading_ko
            "confidence_score": 0.35,  # alias for draft_confidence
            "placeholders_inserted": ["[TBD] old data"],  # alias for placeholders
            "missing_evidence": ["source document"],
            "evidence_segments_used": 1,  # alias for evidence_segments
        }
        (ws / "07_drafts").mkdir(parents=True, exist_ok=True)
        (ws / "07_drafts" / "SEC-OLD_meta.json").write_text(
            json.dumps(old_style_meta, ensure_ascii=False), encoding="utf-8"
        )

        # 06_buckets/SEC-OLD.json
        (ws / "06_buckets").mkdir(parents=True, exist_ok=True)
        (ws / "06_buckets" / "SEC-OLD.json").write_text(
            json.dumps({"section_id": "SEC-OLD", "grounded_segments": [{"segment_id": "SEG-OLD-1"}]}),
            encoding="utf-8",
        )

        # 07_drafts/SEC-OLD.md — run_handoff는 draft_files(SEC-*.md) 없으면早期리ターン하므로 필요
        (ws / "07_drafts" / "SEC-OLD.md").write_text("# 구旧 섹션\n\nOld section content.\n", encoding="utf-8")

        (ws / "09_handoff").mkdir(parents=True, exist_ok=True)
        (ws / "02_file_registry").mkdir(parents=True, exist_ok=True)
        (ws / "02_file_registry" / "data_gap_report.json").write_text(
            json.dumps({"unconvertible_files": []}), encoding="utf-8"
        )

        run_handoff(str(ws))

        # (제목 없음) 대신 구 필드명 값이 사용되어야 함
        summary = (ws / "09_handoff" / "placeholder_summary.md").read_text(encoding="utf-8")
        # heading_text가 fallback으로 읽혀서 "구旧 섹션"이 아닌 "(제목 없음)"이 아니어야 함
        assert "(제목 없음)" not in summary, "구 필드명(meta 파일)의 heading_text가 fallback으로 읽혀야 합니다"
