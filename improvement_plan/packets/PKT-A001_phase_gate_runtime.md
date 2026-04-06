# PKT-A001 — Phase/Gate 런타임 정합성 수정

## 개요

**문제**: SYSIMPROVE-2026-001에서 `phase_rules.json`과 `gate_rules.json`에 P0.5/P1.5와 신규 게이트가 추가됐지만, 실제 파이썬 런타임 코드(run_pipeline.py, state_manager.py, check_gate.py, update_project_state.py)는 여전히 구 8-phase 플로우(`P0→P1→P2→…→P7`)를 사용 중이다.

**효과**: 이 패킷 완료 후 `run_pipeline.py --dry-run`에서 P0.5/P1.5 게이트가 출력되고, `update_project_state.py` 가 P0.5/P1.5 완료 여부를 정확히 판정한다.

---

## 입력 파일 (작업 전 반드시 읽기)

1. `scripts/run_pipeline.py` — PHASE_ORDER, NEXT_PHASE, dry-run 로직
2. `scripts/state_manager.py` — PHASE_ORDER, NEXT_PHASE
3. `scripts/check_gate.py` — NEXT_PHASE, evaluate() 메서드
4. `scripts/update_project_state.py` — phase_order, determine_phase()
5. `orchestration/gate_rules.json` — 새 게이트의 type(human/auto), 조건 파악
6. `orchestration/phase_rules.json` — P0.5/P1.5 진입·종료 조건

---

## 상세 작업

### 작업 1. `scripts/run_pipeline.py` 수정

**백업 먼저**: `cp scripts/run_pipeline.py scripts/run_pipeline.py.bak`

**변경 1-A. PHASE_ORDER (line 46)**
```python
# 변경 전
PHASE_ORDER = ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7"]

# 변경 후
PHASE_ORDER = ["P0", "P0.5", "P1", "P1.5", "P2", "P3", "P4", "P5", "P6", "P7"]
```

**변경 1-B. NEXT_PHASE 딕셔너리 (line 48)**
```python
# 변경 전
NEXT_PHASE = {
    "P0": "P1",
    "P1": "P2",
    "P2": "P3",
    ...
}

# 변경 후
NEXT_PHASE = {
    "P0": "P0.5",
    "P0.5": "P1",
    "P1": "P1.5",
    "P1.5": "P2",
    "P2": "P3",
    "P3": "P4",
    "P4": "P5",
    "P5": "P6",
    "P6": "P7",
    "P7": None,
}
```

**변경 1-C. dry-run 로직의 human gate 목록**

dry-run 섹션(line ~837)에서 human gate와 auto gate를 분기하는 조건을 찾는다:
```python
# 변경 전 (P2_to_P3, P5_to_P6만 human gate로 처리)
if gate_name in ("P2_to_P3", "P5_to_P6"):
    result = gate_eval.evaluate(gate_name)
else:
    result = gate_eval.evaluate_auto_gate(phase, next_phase)

# 변경 후 (P1.5_to_P2 추가 — gate_rules.json에서 human 게이트임을 확인)
if gate_name in ("P2_to_P3", "P5_to_P6", "P1.5_to_P2"):
    result = gate_eval.evaluate(gate_name)
else:
    result = gate_eval.evaluate_auto_gate(phase, next_phase)
```

> **주의**: gate_name은 f"{phase}_to_{next_phase}" 형태로 자동 생성된다.
> P0.5→P1 은 auto gate(gate_rules.json 확인), P1.5→P2 는 human gate.

**변경 1-D. PipelineEngine._execute_phase() 내 phase 분기 로직**

`_execute_phase()` 또는 `_run_phase()` 메서드에서 phase별 실행 함수를 호출하는 분기가 있다. P0.5와 P1.5를 처리하는 브랜치를 추가한다:

```python
# 예시 — 기존 코드 패턴에 맞게 추가
elif phase == "P0.5":
    # intake-interviewer 에이전트 실행
    # run_intake_interviewer.py가 없으면 상태만 기록하고 skip
    return PhaseResult(
        phase="P0.5",
        success=True,
        message="P0.5 intake interview: 에이전트 프롬프트 기반 수동 실행 또는 run_intake_interviewer.py 호출",
        outputs=[],
    )
elif phase == "P1.5":
    # toc_draft 생성 (run_toc_planner.py --toc-draft 호출)
    # PKT-A003 완료 후 실제 구현 — 지금은 상태 기록만
    return PhaseResult(
        phase="P1.5",
        success=True,
        message="P1.5 toc discussion: run_toc_planner.py --toc-draft 호출 필요 (PKT-A003 구현 후 연결)",
        outputs=[],
    )
```

> **중요**: PKT-A003 완료 전에는 실제 실행 로직 없이 stub으로 처리한다.
> PKT-A003 완료 후 PKT-A004에서 연결한다.

---

### 작업 2. `scripts/state_manager.py` 수정

**백업 먼저**: `cp scripts/state_manager.py scripts/state_manager.py.bak`

**변경 2-A. PHASE_ORDER (line 39)**
```python
# 변경 전
PHASE_ORDER = ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7"]

# 변경 후
PHASE_ORDER = ["P0", "P0.5", "P1", "P1.5", "P2", "P3", "P4", "P5", "P6", "P7"]
```

**변경 2-B. NEXT_PHASE 딕셔너리 (line 41)**
```python
# 변경 후
NEXT_PHASE = {
    "P0": "P0.5",
    "P0.5": "P1",
    "P1": "P1.5",
    "P1.5": "P2",
    "P2": "P3",
    "P3": "P4",
    "P4": "P5",
    "P5": "P6",
    "P6": "P7",
    "P7": None,
}
```

**변경 2-C. `get_current_phase()` 또는 `advance_phase()` 내 phase 순서 의존 로직**

state_manager.py 안에서 PHASE_ORDER 리스트를 index로 사용하는 코드를 찾는다.
예시: `idx = PHASE_ORDER.index(current_phase)` → PHASE_ORDER 업데이트로 자동 처리됨.
별도 하드코딩된 phase 비교 로직이 있으면 동일하게 수정한다.

---

### 작업 3. `scripts/check_gate.py` 수정

**백업 먼저**: `cp scripts/check_gate.py scripts/check_gate.py.bak`

**변경 3-A. NEXT_PHASE 딕셔너리 (line 34)**
```python
# 변경 후 (run_pipeline.py와 동일하게)
NEXT_PHASE = {
    "P0": "P0.5",
    "P0.5": "P1",
    "P1": "P1.5",
    "P1.5": "P2",
    "P2": "P3",
    "P3": "P4",
    "P4": "P5",
    "P5": "P6",
    "P6": "P7",
    "P7": None,
}
```

**변경 3-B. `evaluate()` 메서드 (line 586)**

`evaluate()` 메서드에 새 게이트 2개를 추가한다:

```python
def evaluate(
    self, gate_name: str, from_phase: Optional[str] = None, to_phase: Optional[str] = None
) -> dict[str, Any]:
    """Evaluate a gate by name."""
    if gate_name == "P2_to_P3":
        return self.evaluate_p2_to_p3()
    elif gate_name == "P5_to_P6":
        return self.evaluate_p5_to_p6()
    # ── 신규 추가 ──
    elif gate_name in ("P0.5_to_P1", "GATE-P05-TO-P1"):
        return self.evaluate_p05_to_p1()
    elif gate_name in ("P1.5_to_P2", "GATE-P15-TO-P2"):
        return self.evaluate_p15_to_p2()
    # ── 기존 유지 ──
    elif gate_name == "auto":
        if not from_phase or not to_phase:
            raise ValueError("--from-phase and --to-phase required for auto gate")
        return self.evaluate_auto_gate(from_phase, to_phase)
    else:
        raise ValueError(f"Unknown gate: {gate_name}")
```

**변경 3-C. 새 메서드 `evaluate_p05_to_p1()` 추가**

`GateEvaluator` 클래스 내에 추가 (evaluate_p2_to_p3와 유사한 위치):

```python
def evaluate_p05_to_p1(self) -> dict[str, Any]:
    """P0.5 → P1 자동 게이트: intake_manifest.json 존재 확인."""
    blocking_conditions = []

    intake_path = self.workspace / "00_definition" / "intake_manifest.json"
    if not intake_path.exists():
        blocking_conditions.append("intake_manifest_missing")

    if blocking_conditions:
        return {
            "gate": "P0.5_to_P1",
            "result": "blocked",
            "blocking_conditions": blocking_conditions,
            "auto_conditions_met": False,
            "can_override": True,
            "message": "P0.5→P1 차단: intake_manifest.json 없음. "
                       "인테이크 인터뷰를 완료하거나 intake_manifest.json을 수동 생성하세요.",
            "exit_code": EXIT_BLOCKED,
        }
    return {
        "gate": "P0.5_to_P1",
        "result": "passed",
        "blocking_conditions": [],
        "auto_conditions_met": True,
        "can_override": False,
        "message": "P0.5→P1 자동 통과: intake_manifest.json 확인됨.",
        "exit_code": EXIT_AUTO_PASSED,
    }
```

**변경 3-D. 새 메서드 `evaluate_p15_to_p2()` 추가**

```python
def evaluate_p15_to_p2(self) -> dict[str, Any]:
    """P1.5 → P2 사람 승인 게이트: toc_draft.json 존재 + 게이트 승인 확인."""
    blocking_conditions = []

    toc_draft_path = self.workspace / "05_planning" / "toc_draft.json"
    if not toc_draft_path.exists():
        blocking_conditions.append("toc_draft_missing")

    # 게이트 승인 상태 확인
    gate_passed = self._gate_is_passed("P1.5_to_P2")
    if not gate_passed:
        blocking_conditions.append("p15_to_p2_not_approved")

    if blocking_conditions:
        return {
            "gate": "P1.5_to_P2",
            "result": "human_approval_required",
            "blocking_conditions": blocking_conditions,
            "auto_conditions_met": False,
            "can_override": False,
            "message": "P1.5→P2 사람 승인 필요: toc_draft.json 검토 후 "
                       "'sustainreport approve P1.5_to_P2 --workspace ...' 실행 필요.",
            "exit_code": EXIT_HUMAN_APPROVAL,
        }
    return {
        "gate": "P1.5_to_P2",
        "result": "passed",
        "blocking_conditions": [],
        "auto_conditions_met": True,
        "can_override": False,
        "message": "P1.5→P2 통과: toc_draft 승인됨.",
        "exit_code": EXIT_PASSED,
    }
```

> **`_gate_is_passed()` 메서드 확인**: check_gate.py 또는 state_manager.py에 이미 구현돼 있는지 확인 후 재사용한다.
> 없으면 approval_gates.json에서 해당 gate의 status == "approved"를 확인하는 로직을 직접 작성한다.

**변경 3-E. CLI `--gate` 옵션 help 텍스트 업데이트**

```python
# 변경 전
help="Gate to evaluate: P2_to_P3, P5_to_P6, or auto"

# 변경 후
help="Gate to evaluate: P2_to_P3, P5_to_P6, P0.5_to_P1, P1.5_to_P2, or auto"
```

---

### 작업 4. `scripts/update_project_state.py` 수정

**백업 먼저**: `cp scripts/update_project_state.py scripts/update_project_state.py.bak`

**변경 4-A. `determine_phase()` 내 phase_order (line 30)**
```python
# 변경 전
phase_order = ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7"]

# 변경 후
phase_order = ["P0", "P0.5", "P1", "P1.5", "P2", "P3", "P4", "P5", "P6", "P7"]
```

**변경 4-B. P0.5 완료 판정 로직 추가**

기존 `p0_done` 판정 아래, `p1_done` 판정 위에 삽입:

```python
# P0.5: complete if intake_manifest.json exists
p05_done = (workspace / "00_definition" / "intake_manifest.json").exists()
# 하위 호환: intake_manifest가 없어도 P1이 완료돼 있으면 P0.5를 암묵적으로 완료로 처리
if not p05_done and p1_done:
    p05_done = True
```

**변경 4-C. P1.5 완료 판정 로직 추가**

`p1_done` 판정 아래, `p2_done` 판정 위에 삽입:

```python
# P1.5: complete if toc_draft.json exists AND P1.5_to_P2 gate is passed
toc_draft_path = workspace / "05_planning" / "toc_draft.json"
p15_toc_exists = toc_draft_path.exists()
p15_gate_passed = _gate_is_passed(workspace, "P1.5_to_P2")
p15_done = p15_toc_exists and p15_gate_passed
# 하위 호환: toc_draft 없어도 P2가 완료(structure_index 등 존재)이면 P1.5 암묵적 완료
if not p15_done and _planning_outputs_exist(workspace):
    p15_done = True
```

**변경 4-D. `completed` 딕셔너리 업데이트**

```python
completed = {
    "P0": p0_done,
    "P0.5": p05_done,   # 추가
    "P1": p1_done,
    "P1.5": p15_done,   # 추가
    "P2": p2_done,
    "P3": p3_done,
    "P4": p4_done,
    "P5": p5_done,
    "P6": p6_done,
    "P7": p7_done,
}
```

**변경 4-E. `project_state.json` 출력 스키마 확인**

`update_project_state.py`가 최종 저장하는 `project_state.json`의 `phases` 필드에 P0.5, P1.5가 포함되는지 확인. `phase_status` dict가 `completed`에서 자동 생성된다면 추가 수정 불필요. 그렇지 않으면 phases 목록 하드코딩 부분도 수정한다.

---

## 완료 기준 체크리스트

실행 후 아래 명령으로 검증한다:

```bash
# 1. dry-run 게이트 목록 확인 — P0.5_to_P1, P1.5_to_P2 출력돼야 함
uv run python scripts/run_pipeline.py --workspace workspaces/PRJ-2026-KRS-001 --dry-run

# 2. 상태 재계산 확인 — P0.5, P1.5 필드가 phase_status에 포함돼야 함
uv run python scripts/update_project_state.py --workspace workspaces/PRJ-2026-KRS-001

# 3. 새 게이트 직접 평가 — 오류 없이 결과 반환돼야 함
uv run python scripts/check_gate.py --gate P0.5_to_P1 --workspace workspaces/PRJ-2026-KRS-001
uv run python scripts/check_gate.py --gate P1.5_to_P2 --workspace workspaces/PRJ-2026-KRS-001

# 4. 기존 테스트 회귀 없음 확인
uv run pytest tests/ -x -q
```

모든 체크 통과 시 IMPLEMENTATION_SPEC_002.json의 PKT-A001 status를 "done"으로 업데이트한다.

---

## 결정 원칙

- `_gate_is_passed()` 함수가 이미 check_gate.py에 있으면 재사용. 없으면 approval_gates.json을 직접 파싱한다.
- P0.5/P1.5의 하위 호환 처리(암묵적 완료)는 기존 PRJ-2026-KRS-001 워크스페이스가 깨지지 않도록 하기 위함이다. 제거하지 말 것.
- 테스트가 깨지면 새 기능을 추가하기 전에 먼저 수정한다.
