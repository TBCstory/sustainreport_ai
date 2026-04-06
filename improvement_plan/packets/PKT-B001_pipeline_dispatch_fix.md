# PKT-B001: run_pipeline.py dispatch 정합성 — P0.5/P1.5 실행 경로 연결

## 목표
run_pipeline.py가 P0.5/P1.5를 **실제로 실행**하게 만든다. 현재는 dispatch 분기에 case가 없어 `else: continue`로 건너뜀.

## 문제 진단 (3건)

### D1. Phase 범위 필터가 문자열 비교 (line 614-616)
```python
# 현재 (위험)
if phase < self.start_phase:    # 문자열 비교
    continue
if phase > self.end_phase:
    break
```
P0.5/P1.5는 현재 ASCII 우연으로 동작하지만, 의미적으로 틀림.

### D2. Dispatch 분기에 P0.5/P1.5 case 없음 (line 651-672)
```python
if phase == "P0":
    ...
elif phase == "P1":
    ...
# P0.5, P1.5에 대한 elif가 없음
else:
    continue  # ← line 672: P0.5/P1.5가 여기로 빠짐
```

### D3. _run_phase_p0_5/_run_phase_p1_5가 stub (line 106-137)
항상 success=True 반환. 파일이 없어도 성공.

## 입력 파일 (반드시 먼저 읽을 것)
- `/Users/lj_homemac/tools/sustainreport_ai/scripts/run_pipeline.py` — 전체
- `/Users/lj_homemac/tools/sustainreport_ai/scripts/run_toc_planner.py` — `run_toc_draft()` 함수 시그니처 확인
- `/Users/lj_homemac/tools/sustainreport_ai/orchestration/phase_rules.json` — P0.5, P1.5 정의 확인

## 상세 작업

### 작업 1: Phase 범위 필터를 인덱스 기반으로 교체

**위치**: `run_pipeline.py` line 614-616

**변경 전:**
```python
if phase < self.start_phase:
    continue
if phase > self.end_phase:
    break
```

**변경 후:**
```python
phase_idx = PHASE_ORDER.index(phase)
start_idx = PHASE_ORDER.index(self.start_phase)
end_idx = PHASE_ORDER.index(self.end_phase)
if phase_idx < start_idx:
    continue
if phase_idx > end_idx:
    break
```

**최적화**: `start_idx`와 `end_idx`는 루프 밖에서 한 번만 계산한다.
- 루프 진입 전에 `start_idx = PHASE_ORDER.index(self.start_phase)`, `end_idx = PHASE_ORDER.index(self.end_phase)` 선언
- 루프 안에서는 `phase_idx = i` (enumerate의 i를 그대로 사용 — PHASE_ORDER를 enumerate하고 있으므로 i가 곧 인덱스)

### 작업 2: Dispatch 분기에 P0.5/P1.5 추가

**위치**: `run_pipeline.py` line 651-672 사이

P0 case 다음, P1 case 이전에 삽입:
```python
elif phase == "P0.5":
    phase_result = runner(self.workspace)
```

P1 case 다음, P2 case 이전에 삽입:
```python
elif phase == "P1.5":
    phase_result = runner(self.workspace)
```

**인자 시그니처**: _run_phase_p0_5(workspace)와 _run_phase_p1_5(workspace)는 workspace만 받으므로 P0과 동일한 패턴.

### 작업 3: _run_phase_p0_5 실제 동작으로 변경

**위치**: `run_pipeline.py` line 106-120

**변경 내용:**
- `intake_manifest.json`이 존재하면 → success=True (현행 유지)
- `intake_manifest.json`이 존재하지 않으면 → **success=False**, message에 "intake_manifest.json 미생성. `run_intake_interview.py` 실행 또는 수동 생성 필요" 기재
- 즉, "아무것도 안 했는데 성공" 상태를 없앤다

```python
def _run_phase_p0_5(workspace: Path) -> PhaseResult:
    """P0.5: 인테이크 인터뷰 — intake_manifest.json 존재 확인."""
    start = time.monotonic()
    intake = workspace / "00_definition" / "intake_manifest.json"
    duration = time.monotonic() - start
    if intake.exists():
        return PhaseResult(
            phase="P0.5",
            success=True,
            duration_seconds=duration,
            message="P0.5 완료: intake_manifest.json 확인됨.",
            outputs=[str(intake.relative_to(workspace))],
        )
    else:
        return PhaseResult(
            phase="P0.5",
            success=False,
            duration_seconds=duration,
            message="P0.5 차단: intake_manifest.json 미생성. 인테이크 인터뷰를 먼저 수행하세요.",
            outputs=[],
        )
```

### 작업 4: _run_phase_p1_5 실제 동작으로 변경

**위치**: `run_pipeline.py` line 123-137

**변경 내용:**
- `toc_draft.json`이 존재하면 → success=True
- `toc_draft.json`이 없으면 → `run_toc_draft()` 호출 시도
  - import: `from scripts.run_toc_planner import run_toc_draft`
  - 호출: `result = run_toc_draft(workspace)`
  - result["success"]이면 success=True
  - result["waiting"]이면 success=True, message에 게이트 대기 상태 기재
  - 실패면 success=False

```python
def _run_phase_p1_5(workspace: Path) -> PhaseResult:
    """P1.5: 목차 논의 — toc_draft.json 생성 또는 존재 확인."""
    start = time.monotonic()
    toc_draft = workspace / "05_planning" / "toc_draft.json"

    if toc_draft.exists():
        duration = time.monotonic() - start
        return PhaseResult(
            phase="P1.5",
            success=True,
            duration_seconds=duration,
            message="P1.5 완료: toc_draft.json 확인됨.",
            outputs=[str(toc_draft.relative_to(workspace))],
        )

    # toc_draft 미존재 → 생성 시도
    try:
        from scripts.run_toc_planner import run_toc_draft
        result = run_toc_draft(workspace)
        duration = time.monotonic() - start

        if result.get("success"):
            outputs = result.get("outputs", [])
            msg = "P1.5 완료: toc_draft.json 생성됨."
            if result.get("waiting"):
                msg = f"P1.5 대기: {result.get('gate_name', 'P1.5_to_P2')} 승인 대기 중."
            return PhaseResult(
                phase="P1.5", success=True,
                duration_seconds=duration, message=msg, outputs=outputs,
            )
        else:
            return PhaseResult(
                phase="P1.5", success=False,
                duration_seconds=duration,
                message=f"P1.5 실패: {result.get('message', 'toc_draft 생성 실패')}",
                outputs=[],
            )
    except Exception as e:
        duration = time.monotonic() - start
        return PhaseResult(
            phase="P1.5", success=False,
            duration_seconds=duration,
            message=f"P1.5 차단: toc_draft.json 미생성. run_toc_planner.py --toc-draft 실행 필요. ({e})",
            outputs=[],
        )
```

**import 위치**: 함수 내부 lazy import로 순환 참조 방지.

## 완료 기준
1. `uv run pytest tests/ -q` — 전체 통과 (기존 123개 + 변경으로 인한 수정 포함)
2. 수동 검증 시나리오:
   - `PipelineEngine(start_phase='P0.5', end_phase='P0.5')` → intake 없으면 `success=False`, `phases_executed=['P0.5']`
   - `PipelineEngine(start_phase='P1.5', end_phase='P1.5')` → toc_draft 없으면 `success=False` 또는 생성 시도
   - `PipelineEngine(start_phase='P0', end_phase='P7')` → phases_executed에 P0.5, P1.5가 포함됨
3. `else: continue` 분기로 P0.5/P1.5가 빠지는 경로가 **완전히 제거**됨

## 결정 원칙
- `_run_phase_p1_5`에서 `run_toc_draft()` 호출이 실패할 경우 (LLM API 불가 등): exception을 잡아서 success=False로 반환. 파이프라인을 중단하되 크래시하지 않음.
- `skip_approvals=True`일 때 P0.5의 intake_manifest 미존재: 그래도 success=False. skip_approvals는 게이트 승인을 건너뛰는 것이지, 필수 산출물 부재를 무시하는 것이 아님.
- phase 범위 필터에서 `PHASE_ORDER.index()`가 ValueError를 낼 수 있음: `__init__`에서 start_phase/end_phase 유효성을 이미 검증하므로 추가 방어 불필요.

## 영향 범위
- `scripts/run_pipeline.py` — 주 수정 대상
- 기존 테스트 중 pipeline mock 관련 테스트가 깨질 수 있음 → 수정
- 새 테스트는 PKT-B005에서 추가 (이 패킷에서는 기존 테스트 통과만 확인)
