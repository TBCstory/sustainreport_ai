# PKT-B005: E2E 런타임 회귀 테스트 — dispatch·handoff·toc intake 실행 검증

## 목표
PKT-B001~B004에서 수정한 내용을 **다시는 regression이 들어오지 못하게** 테스트로 고정한다.

## 전제 조건
PKT-B001, B002, B003, B004 모두 완료.

## 입력 파일 (반드시 먼저 읽을 것)
- `/Users/lj_homemac/tools/sustainreport_ai/scripts/run_pipeline.py` — dispatch 수정 상태 확인
- `/Users/lj_homemac/tools/sustainreport_ai/scripts/run_handoff.py` — 필드명 수정 상태 확인
- `/Users/lj_homemac/tools/sustainreport_ai/scripts/run_toc_planner.py` — intake 키 수정 상태 확인
- `/Users/lj_homemac/tools/sustainreport_ai/tests/test_phase_transitions.py` — 기존 테스트 확인
- `/Users/lj_homemac/tools/sustainreport_ai/tests/test_run_toc_planner.py` — 기존 테스트 확인

## 상세 작업

### 작업 1: tests/test_run_pipeline_dispatch.py 신규 생성

**목적**: run_pipeline.py dispatch가 P0.5/P1.5를 실제로 실행하는지 검증

**테스트 케이스:**

```python
class TestPipelineDispatchNewPhases:
    """P0.5/P1.5가 dispatch에서 건너뛰어지지 않는지 검증."""

    def test_p05_dispatched_and_fails_without_intake(self, tmp_workspace):
        """P0.5만 실행: intake_manifest 없으면 success=False, phases_executed=['P0.5']."""
        engine = PipelineEngine(
            workspace=tmp_workspace,
            start_phase="P0.5",
            end_phase="P0.5",
            skip_approvals=True,
        )
        result = engine.run()
        assert "P0.5" in result.phases_executed
        assert not result.success  # intake 없으므로 실패

    def test_p05_dispatched_and_succeeds_with_intake(self, tmp_workspace):
        """P0.5만 실행: intake_manifest 있으면 success=True."""
        (tmp_workspace / "00_definition" / "intake_manifest.json").write_text("{}")
        engine = PipelineEngine(
            workspace=tmp_workspace,
            start_phase="P0.5",
            end_phase="P0.5",
            skip_approvals=True,
        )
        result = engine.run()
        assert "P0.5" in result.phases_executed
        # success는 intake 존재 여부에 따라

    def test_p15_dispatched_not_silent_pass(self, tmp_workspace):
        """P1.5만 실행: toc_draft 없으면 phases_executed에 P1.5가 포함되고 silent pass 아님."""
        engine = PipelineEngine(
            workspace=tmp_workspace,
            start_phase="P1.5",
            end_phase="P1.5",
            skip_approvals=True,
        )
        result = engine.run()
        assert "P1.5" in result.phases_executed
        # 빈 phases_executed가 절대 안 됨
        assert len(result.phases_executed) > 0

    def test_full_pipeline_includes_new_phases(self, tmp_workspace):
        """P0~P7 전체 실행: phases_executed에 P0.5, P1.5 포함."""
        # 최소한의 fixture: intake_manifest + toc_draft
        (tmp_workspace / "00_definition").mkdir(parents=True, exist_ok=True)
        (tmp_workspace / "00_definition" / "intake_manifest.json").write_text("{}")
        (tmp_workspace / "05_planning").mkdir(parents=True, exist_ok=True)
        (tmp_workspace / "05_planning" / "toc_draft.json").write_text('{"approved": true}')

        engine = PipelineEngine(
            workspace=tmp_workspace,
            start_phase="P0",
            end_phase="P2",  # P2까지만 (P3 이후는 더 많은 fixture 필요)
            skip_approvals=True,
        )
        result = engine.run()
        assert "P0.5" in result.phases_executed
        assert "P1.5" in result.phases_executed

    def test_phase_range_filter_uses_index_not_string(self):
        """Phase 범위 필터가 인덱스 기반인지 검증."""
        from scripts.run_pipeline import PHASE_ORDER
        # P0.5는 P0과 P1 사이에 있어야 함
        assert PHASE_ORDER.index("P0.5") == PHASE_ORDER.index("P0") + 1
        assert PHASE_ORDER.index("P1.5") == PHASE_ORDER.index("P1") + 1
```

### 작업 2: tests/test_run_handoff_quality.py 신규 생성

**목적**: run_handoff.py 산출물이 실제 필드값을 반영하는지 검증

**테스트 케이스:**

```python
class TestHandoffOutputQuality:
    """run_handoff 산출물이 (제목 없음)/0 대신 실제 값을 출력하는지 검증."""

    def _setup_sample_workspace(self, tmp_path):
        """최소 fixture: blueprint + draft meta + draft MD."""
        # blueprint with heading_ko
        # draft meta with heading_ko, draft_confidence, evidence_segments, placeholders
        # draft MD with [추후 기재] placeholders
        ...

    def test_placeholder_summary_shows_real_heading(self, tmp_path):
        """placeholder_summary.md에 (제목 없음)이 없어야 함."""
        ws = self._setup_sample_workspace(tmp_path)
        # run handoff
        summary = (ws / "09_handoff" / "placeholder_summary.md").read_text()
        assert "(제목 없음)" not in summary
        assert "안전보건" in summary  # fixture의 heading_ko

    def test_data_gap_shows_real_confidence(self, tmp_path):
        """data_gap_priority.md에 실제 confidence 숫자가 표시."""
        ws = self._setup_sample_workspace(tmp_path)
        gap = (ws / "09_handoff" / "data_gap_priority.md").read_text()
        assert "0." in gap  # 0.55 등의 숫자
        assert "None" not in gap

    def test_checklist_has_items(self, tmp_path):
        """consultant_review_checklist.json에 항목이 1개 이상."""
        ws = self._setup_sample_workspace(tmp_path)
        checklist = json.loads((ws / "09_handoff" / "consultant_review_checklist.json").read_text())
        assert len(checklist) > 0

    def test_review_priority_score_present(self, tmp_path):
        """data_gap_priority에 review_priority_score 컬럼 존재."""
        ws = self._setup_sample_workspace(tmp_path)
        gap = (ws / "09_handoff" / "data_gap_priority.md").read_text()
        assert "priority" in gap.lower() or "우선순위" in gap

    def test_alias_fallback_reads_old_meta(self, tmp_path):
        """구 필드명(confidence_score, heading_text)으로 된 meta도 읽힘."""
        # old-style meta fixture
        ...
```

### 작업 3: tests/test_run_toc_planner.py에 intake 키 테스트 추가

**기존 파일에 추가:**

```python
def test_toc_draft_prompt_uses_correct_intake_keys(self, tmp_workspace):
    """_build_toc_draft_prompt가 custom_toc_reference/section_priority를 프롬프트에 포함."""
    intake = {
        "A_structure": {
            "toc_style": "framework",
            "custom_toc_reference": "GRI Standards 2021",
            "section_priority": ["환경", "사회"],
            "scope_inclusions": [],
            "scope_exclusions": [],
        }
    }
    segment_manifest = {"segments": []}

    from scripts.run_toc_planner import _build_toc_draft_prompt
    prompt = _build_toc_draft_prompt(segment_manifest, intake)

    assert "GRI Standards 2021" in prompt
    assert "환경" in prompt or "사회" in prompt
```

### 작업 4: conftest.py에 공통 fixture 추가

tmp_workspace fixture가 없다면 `tests/conftest.py`에 추가:

```python
@pytest.fixture
def tmp_workspace(tmp_path):
    """최소 워크스페이스 구조."""
    dirs = [
        "00_definition", "01_raw", "02_file_registry",
        "03_normalized_md", "04_segments", "05_planning",
        "06_buckets", "07_drafts", "08_review",
        "09_handoff", "10_evidence_pack",
        "guidance", "context_bus",
    ]
    for d in dirs:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return tmp_path
```

## 완료 기준
1. 새 테스트 파일 2개 이상 생성: `test_run_pipeline_dispatch.py`, `test_run_handoff_quality.py`
2. 기존 `test_run_toc_planner.py`에 1개 이상 테스트 추가
3. `uv run pytest tests/ -q` — 전체 통과 (기존 + 신규)
4. 신규 테스트 중 dispatch 관련 최소 4개, handoff 관련 최소 4개

## 결정 원칙
- 테스트에서 LLM 호출이 필요한 부분은 mock (unittest.mock.patch)
- 실제 파일 I/O는 tmp_path로 격리
- 테스트 fixture는 최소한으로: 검증 대상 기능에 필요한 파일만 생성
- 기존 테스트 파일의 구조/패턴을 따름 (import 스타일, fixture 명명 등)

## 영향 범위
- `tests/test_run_pipeline_dispatch.py` — 신규
- `tests/test_run_handoff_quality.py` — 신규
- `tests/test_run_toc_planner.py` — 테스트 추가
- `tests/conftest.py` — fixture 추가 (필요 시)
