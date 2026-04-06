# PKT-A004 — 회귀 테스트 — 새 플로우 검증

## 개요

**문제**: 현재 pytest 106개는 모두 통과하지만 PKT-A001~A003의 핵심 개선(P0.5/P1.5 phase transition, normalize.py 통합, toc_draft 생성/승인 흐름)을 검증하는 테스트가 없다. 다음 패치에서 회귀가 발생해도 탐지할 수 없다.

**효과**: 이 패킷 완료 후 pytest가 새 플로우를 직접 검증하는 테스트를 포함한다. 특히 구 경로에 의존하던 기존 테스트도 새 경로를 검증하도록 업데이트된다.

---

## 입력 파일 (작업 전 반드시 읽기)

1. `tests/test_run_ingestion.py` — 현재 ingestion 테스트 구조 파악
2. `tests/test_run_toc_planner.py` — 현재 planner 테스트 구조 파악
3. `tests/test_state_manager.py` — 현재 state manager 테스트 구조 파악
4. `scripts/run_ingestion.py` — PKT-A002 완료 후 버전
5. `scripts/run_toc_planner.py` — PKT-A003 완료 후 버전
6. `scripts/update_project_state.py` — PKT-A001 완료 후 버전

> **주의**: 이 패킷은 PKT-A001, PKT-A002, PKT-A003이 모두 완료된 후 실행한다.

---

## 상세 작업

### 작업 1. `tests/test_run_ingestion.py` 업데이트

기존 테스트를 유지하면서 아래 테스트 케이스를 추가한다.

#### 추가 테스트 1-A: normalize.py 경로 사용 확인

```python
def test_ingestion_uses_normalize_process_single_file(tmp_path, monkeypatch):
    """run_ingestion이 normalize.process_single_file을 호출하는지 확인한다."""
    from scripts import run_ingestion
    from scripts import normalize as norm_module

    call_log = []

    def mock_process_single_file(input_path, output_path, workspace_path=None,
                                  extract_segments=False, force=False, force_ocr=False):
        call_log.append(str(input_path))
        # 빈 md 파일 생성 (정상 변환 시뮬레이션)
        output_path.write_text(
            "---\nfile_id: F-0001\nconversion_method: markitdown\n---\n\n테스트 내용\n",
            encoding="utf-8"
        )
        return {"conversion_method": "markitdown", "char_count": 10}

    monkeypatch.setattr(norm_module, "process_single_file", mock_process_single_file)

    # 워크스페이스 설정
    ws = tmp_path / "PRJ-TEST"
    raw_dir = ws / "01_raw"
    raw_dir.mkdir(parents=True)
    test_file = raw_dir / "test.pdf"
    test_file.write_bytes(b"%PDF-1.4 test content")

    result = run_ingestion.run_ingestion(workspace=str(ws))

    assert len(call_log) > 0, "process_single_file이 호출되지 않았습니다 (구 markitdown 직접 호출 경로 사용 중)"
    assert str(test_file) in call_log
```

#### 추가 테스트 1-B: data_gap_report.json 생성 확인

```python
def test_ingestion_creates_data_gap_report(tmp_path, monkeypatch):
    """run_ingestion 완료 후 data_gap_report.json이 생성되는지 확인한다."""
    from scripts import run_ingestion
    from scripts import normalize as norm_module

    def mock_process_single_file(input_path, output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "---\nfile_id: F-0001\nconversion_method: markitdown\n---\n\n내용\n",
            encoding="utf-8"
        )
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
```

#### 추가 테스트 1-C: unconvertible_files.json 생성 확인

```python
def test_ingestion_creates_unconvertible_files(tmp_path, monkeypatch):
    """변환 실패 파일이 있을 때 unconvertible_files.json이 생성되는지 확인한다."""
    from scripts import run_ingestion
    from scripts import normalize as norm_module

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
```

---

### 작업 2. `tests/test_run_toc_planner.py` 업데이트

기존 테스트(3개 출력 파일 확인)를 유지하면서 아래를 추가한다.

#### 추가 테스트 2-A: --toc-draft 모드에서 toc_draft.json 생성

```python
def test_toc_draft_mode_creates_toc_draft_json(tmp_path, monkeypatch):
    """--toc-draft 모드 실행 시 05_planning/toc_draft.json이 생성되는지 확인."""
    from scripts import run_toc_planner

    # LLM 호출 mock
    def mock_llm_call(*args, **kwargs):
        return {
            "content": json.dumps({
                "sections": [
                    {"section_id": "SEC-1", "heading_text": "CEO 메시지", "level": 1,
                     "parent_section_id": None, "estimated_pages": 2, "frameworks": [], "notes": None},
                    {"section_id": "SEC-2", "heading_text": "지배구조", "level": 1,
                     "parent_section_id": None, "estimated_pages": 5, "frameworks": ["GRI 2-9"], "notes": None},
                ]
            }),
            "run_id": "test-run-001",
        }

    monkeypatch.setattr(run_toc_planner.ModelRouter, "call", mock_llm_call)

    # 워크스페이스 설정
    ws = tmp_path / "PRJ-TEST"
    (ws / "04_segments").mkdir(parents=True)
    (ws / "00_definition").mkdir(parents=True)
    (ws / "04_segments" / "segment_manifest.json").write_text(
        json.dumps({"segments": []}), encoding="utf-8"
    )

    result = run_toc_planner.run_toc_draft(
        workspace=str(ws), skip_approval=True
    )

    assert result["success"] is True
    toc_draft_path = ws / "05_planning" / "toc_draft.json"
    assert toc_draft_path.exists(), "toc_draft.json이 생성되지 않았습니다"

    with open(toc_draft_path, encoding="utf-8") as f:
        toc = json.load(f)

    assert len(toc["sections"]) == 2
    assert toc["status"] == "approved"  # skip_approval=True이므로
```

#### 추가 테스트 2-B: toc_draft 미승인 상태에서 blueprint 단계 차단

```python
def test_blueprint_blocked_without_toc_approval(tmp_path):
    """toc_draft.json 없이 run_toc_planner 기본 모드 실행 시 실패 반환 확인."""
    from scripts import run_toc_planner

    ws = tmp_path / "PRJ-TEST"
    (ws / "04_segments").mkdir(parents=True)
    (ws / "04_segments" / "segment_manifest.json").write_text(
        json.dumps({"segments": []}), encoding="utf-8"
    )

    # toc_draft.json 없는 상태에서 기본 모드 실행
    result = run_toc_planner.run_toc_planner(
        workspace=str(ws), skip_approval=False
    )

    assert result["success"] is False
    assert "toc_draft" in result["message"].lower() or "P1.5" in result["message"]
```

#### 추가 테스트 2-C: GATE-P1.5-TO-P2 승인 후 blueprint 생성 가능

```python
def test_blueprint_proceeds_after_toc_approval(tmp_path, monkeypatch):
    """toc_draft.json이 존재하고 gate가 approved이면 blueprint 생성이 진행됨."""
    from scripts import run_toc_planner

    # LLM mock
    def mock_llm_call(*args, **kwargs):
        return {
            "content": json.dumps({
                "structure_index": {"sections": []},
                "writing_blueprint": {"sections": []},
                "section_manifest": {"sections": []},
            }),
            "run_id": "test-run-002",
        }

    monkeypatch.setattr(run_toc_planner.ModelRouter, "call", mock_llm_call)

    ws = tmp_path / "PRJ-TEST"
    (ws / "04_segments").mkdir(parents=True)
    (ws / "05_planning").mkdir(parents=True)
    (ws / "00_definition").mkdir(parents=True)
    (ws / "04_segments" / "segment_manifest.json").write_text(
        json.dumps({"segments": []}), encoding="utf-8"
    )

    # toc_draft.json 미리 생성 (approved 상태)
    (ws / "05_planning" / "toc_draft.json").write_text(
        json.dumps({"project_id": "PRJ-TEST", "status": "approved", "sections": []}),
        encoding="utf-8"
    )

    # approval_gates.json에 P1.5_to_P2 approved 기록
    (ws / "approval_gates.json").write_text(
        json.dumps({"gates": {"P1.5_to_P2": {"status": "approved"}}}),
        encoding="utf-8"
    )

    result = run_toc_planner.run_toc_planner(
        workspace=str(ws), skip_approval=True
    )

    # 성공하거나 최소한 "toc_draft 미승인" 오류는 발생하지 않아야 함
    assert "toc_draft" not in result.get("message", "").lower() or result["success"] is True
```

---

### 작업 3. `tests/test_phase_transitions.py` 신규 생성

```python
"""
tests/test_phase_transitions.py — P0.5/P1.5 phase transition 검증
"""
import json
import pytest
from pathlib import Path


def _setup_workspace(tmp_path: Path, files: dict) -> Path:
    """워크스페이스 설정 헬퍼."""
    ws = tmp_path / "PRJ-TEST"
    for rel_path, content in files.items():
        full_path = ws / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            full_path.write_text(content, encoding="utf-8")
        else:
            full_path.write_bytes(content)
    return ws


def test_p05_complete_when_intake_manifest_exists(tmp_path):
    """intake_manifest.json이 있으면 P0.5가 complete로 계산됨."""
    from scripts.update_project_state import determine_phase

    # 최소한의 phase_rules mock 또는 실제 phase_rules.json 사용
    ws = _setup_workspace(tmp_path, {
        "00_definition/project_charter.json": json.dumps({"project_id": "PRJ-TEST"}),
        "00_definition/stakeholder_matrix.json": json.dumps({}),
        "00_definition/intake_manifest.json": json.dumps({"project_id": "PRJ-TEST"}),
    })

    phase_rules = {}  # update_project_state는 phase_rules 없이도 동작해야 함
    current_phase, phase_status = determine_phase(ws, phase_rules)

    assert phase_status.get("P0.5") == "complete", \
        f"P0.5가 complete여야 하는데 {phase_status.get('P0.5')}입니다"
    assert current_phase in ("P1", "P1.5", "P2", "P3", "P4", "P5", "P6", "P7"), \
        f"P0.5 완료 후 current_phase가 P1 이후여야 하는데 {current_phase}입니다"


def test_p05_not_in_phase_order_before_fix():
    """PKT-A001 적용 전에는 P0.5가 PHASE_ORDER에 없었음을 문서화 (현재는 있어야 함)."""
    from scripts.run_pipeline import PHASE_ORDER
    assert "P0.5" in PHASE_ORDER, \
        "run_pipeline.PHASE_ORDER에 P0.5가 없습니다 (PKT-A001 미적용)"
    assert "P1.5" in PHASE_ORDER, \
        "run_pipeline.PHASE_ORDER에 P1.5가 없습니다 (PKT-A001 미적용)"


def test_p15_complete_when_toc_draft_approved(tmp_path):
    """toc_draft.json이 있고 P1.5_to_P2 게이트가 approved이면 P1.5가 complete."""
    from scripts.update_project_state import determine_phase

    ws = _setup_workspace(tmp_path, {
        "00_definition/project_charter.json": json.dumps({"project_id": "PRJ-TEST"}),
        "00_definition/stakeholder_matrix.json": json.dumps({}),
        "00_definition/intake_manifest.json": json.dumps({}),
        "02_file_registry/file_registry.json": json.dumps({"files": []}),
        "04_segments/segment_manifest.json": json.dumps({"segments": []}),
        "05_planning/toc_draft.json": json.dumps({"status": "approved", "sections": []}),
        "approval_gates.json": json.dumps({
            "gates": {"P1.5_to_P2": {"status": "approved"}}
        }),
    })

    current_phase, phase_status = determine_phase(ws, {})

    assert phase_status.get("P1.5") == "complete", \
        f"P1.5가 complete여야 하는데 {phase_status.get('P1.5')}입니다"


def test_state_manager_phase_order_includes_new_phases():
    """state_manager의 PHASE_ORDER에 P0.5, P1.5가 포함됨."""
    from scripts.state_manager import PHASE_ORDER

    assert "P0.5" in PHASE_ORDER, "state_manager.PHASE_ORDER에 P0.5 없음"
    assert "P1.5" in PHASE_ORDER, "state_manager.PHASE_ORDER에 P1.5 없음"
    assert PHASE_ORDER.index("P0.5") == PHASE_ORDER.index("P0") + 1
    assert PHASE_ORDER.index("P1.5") == PHASE_ORDER.index("P1") + 1


def test_check_gate_handles_new_gates(tmp_path):
    """check_gate.py가 P0.5_to_P1, P1.5_to_P2 게이트를 처리할 수 있음."""
    from scripts.check_gate import GateEvaluator

    ws = tmp_path / "PRJ-TEST"
    ws.mkdir(parents=True)
    (ws / "00_definition").mkdir()
    (ws / "approval_gates.json").write_text(json.dumps({"gates": {}}), encoding="utf-8")

    evaluator = GateEvaluator(
        workspace=ws,
        orchestration_dir=Path("orchestration"),
    )

    # P0.5_to_P1: intake_manifest 없으므로 blocked 예상
    result_p05 = evaluator.evaluate("P0.5_to_P1")
    assert result_p05["gate"] == "P0.5_to_P1"
    assert result_p05["result"] in ("blocked", "passed")

    # P1.5_to_P2: gate 없으므로 human_approval_required 예상
    result_p15 = evaluator.evaluate("P1.5_to_P2")
    assert result_p15["gate"] == "P1.5_to_P2"
    assert result_p15["result"] in ("human_approval_required", "blocked", "passed")
```

저장 경로: `tests/test_phase_transitions.py`

---

### 작업 4. 기존 테스트 업데이트 — test_run_ingestion.py

기존 테스트 중 `run_markitdown`을 직접 mock하고 있는 테스트가 있다면 `normalize.process_single_file`을 mock하도록 수정한다.

```bash
# 현재 파일에서 run_markitdown mock 사용 여부 확인
grep -n "run_markitdown\|markitdown" tests/test_run_ingestion.py
```

`run_markitdown`을 mock하는 테스트를 찾으면 `process_single_file` mock으로 교체한다.

---

### 작업 5. 전체 테스트 실행 및 결과 확인

```bash
# 전체 테스트 실행
uv run pytest tests/ -v --tb=short 2>&1 | tee /tmp/test_results.txt

# 새 테스트만 확인
uv run pytest tests/test_phase_transitions.py -v
uv run pytest tests/test_run_ingestion.py -v -k "normalize or data_gap or unconvertible"
uv run pytest tests/test_run_toc_planner.py -v -k "toc_draft or p15 or approval"
```

---

## 완료 기준

- `pytest tests/ -q` 실행 시 모든 테스트 통과 (기존 106개 + 새 테스트 전체)
- `tests/test_phase_transitions.py` 내 5개 테스트 모두 green
- `test_ingestion_uses_normalize_process_single_file` — green (PKT-A002 핵심 검증)
- `test_toc_draft_mode_creates_toc_draft_json` — green (PKT-A003 핵심 검증)

---

## 결정 원칙

- LLM 호출은 반드시 mock으로 처리한다. 실제 API 호출 없이 테스트가 통과해야 한다.
- tmp_path fixture를 사용하여 각 테스트가 독립적인 워크스페이스에서 실행된다.
- 기존 테스트가 깨지면 새 테스트를 추가하기 전에 먼저 수정한다.
- `ModelRouter.call`을 monkeypatch하는 경우 반환 형식이 실제 LLM 반환 구조와 일치해야 한다 (`{"content": "...", "run_id": "..."}` 형식 확인 필요).
