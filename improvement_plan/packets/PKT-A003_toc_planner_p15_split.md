# PKT-A003 — run_toc_planner.py P1.5 toc_draft 생성·승인 단계 분리

## 개요

**문제**: `run_toc_planner.py`가 현재 1단계(LLM 호출 1회)로 structure_index, writing_blueprint, section_manifest 3개를 한꺼번에 생성한 뒤 곧바로 P2_to_P3 게이트로 넘어간다. toc_draft.json 생성, GATE-P1.5-TO-P2 승인 대기, 승인 확인 후 blueprint 생성의 3단계 플로우가 없다.

**효과**: 이 패킷 완료 후 `run_toc_planner.py --toc-draft`가 toc_draft.json을 생성하고 컨설턴트 승인 대기 상태를 기록한다. 승인 없이 blueprint 단계를 실행하면 오류가 발생한다. 컨설턴트가 목차를 먼저 검토·수정할 수 있게 된다.

---

## 입력 파일 (작업 전 반드시 읽기)

1. `scripts/run_toc_planner.py` — 전체
2. `agents/toc-planner.md` — Stage 0~2 인터뷰/초안/승인 로직 파악
3. `orchestration/gate_rules.json` — GATE-P15-TO-P2 설정 확인
4. `schemas/` — toc_draft.schema.json이 있으면 읽기 (없으면 이 패킷에서 생성)

---

## 상세 작업

### 작업 1. toc_draft.json 스키마 확인 또는 생성

`schemas/toc_draft.schema.json`이 존재하지 않으면 아래 내용으로 생성한다:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "toc_draft",
  "description": "P1.5 목차 초안 — 컨설턴트 승인 대기",
  "type": "object",
  "required": ["project_id", "generated_at", "status", "sections"],
  "properties": {
    "project_id": { "type": "string" },
    "generated_at": { "type": "string", "format": "date-time" },
    "status": {
      "type": "string",
      "enum": ["draft", "approved", "rejected"],
      "description": "draft: 초안, approved: 컨설턴트 승인 완료, rejected: 재작성 필요"
    },
    "approved_at": { "type": ["string", "null"], "format": "date-time" },
    "approved_by": { "type": ["string", "null"] },
    "rejection_reason": { "type": ["string", "null"] },
    "sections": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["section_id", "heading_text", "level"],
        "properties": {
          "section_id": { "type": "string", "pattern": "^SEC-" },
          "heading_text": { "type": "string" },
          "level": { "type": "integer", "minimum": 1, "maximum": 4 },
          "parent_section_id": { "type": ["string", "null"] },
          "estimated_pages": { "type": ["integer", "null"] },
          "frameworks": {
            "type": "array",
            "items": { "type": "string" },
            "description": "관련 프레임워크 (GRI, TCFD, KSSB 등)"
          },
          "notes": { "type": ["string", "null"] }
        }
      }
    },
    "consultant_notes": { "type": ["string", "null"] },
    "revision_history": { "type": "array", "items": { "type": "object" } }
  }
}
```

저장 경로: `schemas/toc_draft.schema.json`

---

### 작업 2. `run_toc_planner.py`에 `--toc-draft` 모드 추가

**백업 먼저**: `cp scripts/run_toc_planner.py scripts/run_toc_planner.py.bak`

#### 2-A. CLI 옵션 추가

파일 하단의 `@click.command()` 블록에 새 옵션 추가:

```python
@click.option(
    "--toc-draft",
    "toc_draft_only",
    is_flag=True,
    default=False,
    help="P1.5 모드: toc_draft.json만 생성하고 GATE-P1.5-TO-P2 대기 상태를 기록한다.",
)
```

#### 2-B. `main()` 함수에서 모드 분기

```python
def main(workspace, skip_approval, toc_draft_only, ...):
    if toc_draft_only:
        result = run_toc_draft(workspace=workspace, skip_approval=skip_approval)
    else:
        result = run_toc_planner(workspace=workspace, skip_approval=skip_approval)
    ...
```

---

### 작업 3. `run_toc_draft()` 함수 신설

기존 `run_toc_planner()` 함수 위에 새 함수를 추가한다.

이 함수는:
1. segment_manifest.json과 intake_manifest.json(있으면)을 읽는다
2. LLM에 "목차 초안만 생성해달라"는 프롬프트를 전송한다
3. 응답에서 sections 배열을 파싱하여 toc_draft.json을 저장한다
4. GATE-P1.5-TO-P2 대기 상태를 approval_gates.json에 기록한다
5. 반환한다 (blueprint 생성 없음)

```python
def run_toc_draft(
    workspace: str | Path,
    skip_approval: bool = False,
    state_manager: Optional[StateManager] = None,
) -> dict:
    """
    P1.5: 목차 초안(toc_draft.json) 생성 후 컨설턴트 승인 대기.

    반환:
        {
            "success": bool,
            "outputs": list[str],
            "message": str,
            "waiting": bool,       # True이면 게이트 승인 대기 중
            "gate_name": str,
            "gate_status": str,    # "waiting" | "approved" | "skipped"
        }
    """
    workspace = Path(workspace)
    outputs = []

    if state_manager is None:
        state_manager = StateManager(workspace)

    # ── 1. 입력 파일 읽기 ──
    segment_manifest_path = workspace / "04_segments" / "segment_manifest.json"
    if not segment_manifest_path.exists():
        return {
            "success": False,
            "outputs": [],
            "message": "segment_manifest.json이 없습니다. P1(run_ingestion)을 먼저 실행하세요.",
        }

    with open(segment_manifest_path, encoding="utf-8") as f:
        segment_manifest = json.load(f)

    # intake_manifest (없어도 진행 가능)
    intake_manifest_path = workspace / "00_definition" / "intake_manifest.json"
    intake_manifest = {}
    if intake_manifest_path.exists():
        with open(intake_manifest_path, encoding="utf-8") as f:
            intake_manifest = json.load(f)

    # ── 2. LLM 프롬프트 구성 ──
    # toc-planner.md의 Stage 0~2 지침 참조
    toc_prompt = _build_toc_draft_prompt(segment_manifest, intake_manifest)

    # ── 3. LLM 호출 ──
    router = ModelRouter()
    llm_result = router.call(
        agent="toc-planner",
        prompt=toc_prompt,
        workspace=workspace,
    )
    raw_content = llm_result.get("content", "")

    # ── 4. toc_draft 파싱 ──
    try:
        toc_data = _parse_toc_draft(raw_content)
    except ValueError as e:
        return {
            "success": False,
            "outputs": [],
            "message": f"toc_draft 파싱 실패: {e}. LLM 응답: {raw_content[:500]}",
        }

    # ── 5. toc_draft.json 저장 ──
    planning_dir = workspace / "05_planning"
    planning_dir.mkdir(parents=True, exist_ok=True)

    toc_draft_path = planning_dir / "toc_draft.json"
    project_id = workspace.name
    toc_output = {
        "project_id": project_id,
        "generated_at": utc_now(),
        "status": "draft",
        "approved_at": None,
        "approved_by": None,
        "rejection_reason": None,
        "sections": toc_data.get("sections", []),
        "consultant_notes": None,
        "revision_history": [],
    }

    toc_draft_path.write_text(
        json.dumps(toc_output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    outputs.append(str(toc_draft_path.relative_to(workspace)))

    # ── 6. Phase 상태 기록 ──
    state_manager.set_phase_status("P1.5", "complete")
    state_manager.sync()

    # ── 7. GATE-P1.5-TO-P2 처리 ──
    gate_name = "P1.5_to_P2"
    if not skip_approval:
        gate_config = _get_gate_config(gate_name)
        required_approvers = gate_config.get("required_approvers", [])
        state_manager.wait_for_approval(
            gate_name=gate_name,
            required_approvers=required_approvers,
            requester="run_toc_planner --toc-draft",
        )
        state_manager.sync()

        return {
            "success": True,
            "outputs": outputs,
            "message": (
                f"P1.5 완료. toc_draft.json이 생성됐습니다. "
                f"05_planning/toc_draft.json을 검토한 후 "
                f"'sustainreport approve P1.5_to_P2 --workspace ...' 를 실행하거나 "
                f"approval_gates.json을 직접 수정하여 승인해주세요. "
                f"승인 후 'run_toc_planner.py --workspace ...' (--toc-draft 없이)를 실행하면 blueprint가 생성됩니다."
            ),
            "waiting": True,
            "gate_name": gate_name,
            "gate_status": "waiting",
        }
    else:
        # skip-approval 모드: toc_draft를 자동 승인으로 처리
        toc_output["status"] = "approved"
        toc_output["approved_at"] = utc_now()
        toc_output["approved_by"] = "skip_approval"
        toc_draft_path.write_text(
            json.dumps(toc_output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        # approval_gates.json에도 approved로 기록
        _record_gate_approved(workspace, gate_name, approver="skip_approval")

        return {
            "success": True,
            "outputs": outputs,
            "message": "P1.5 완료 (skip-approval 모드: toc_draft 자동 승인됨).",
            "waiting": False,
            "gate_name": gate_name,
            "gate_status": "skipped",
        }
```

---

### 작업 4. `run_toc_planner()` 함수에 P1.5-TO-P2 게이트 체크 추가

기존 `run_toc_planner()` 또는 `run_planning()` 함수의 **시작 부분**에 아래 검증을 추가한다:

```python
def run_toc_planner(workspace, skip_approval=False, state_manager=None):
    workspace = Path(workspace)
    ...

    # ── P1.5-TO-P2 게이트 통과 여부 확인 ──
    toc_draft_path = workspace / "05_planning" / "toc_draft.json"
    gate_p15_passed = _gate_is_passed_local(workspace, "P1.5_to_P2")

    if not skip_approval:
        if not toc_draft_path.exists():
            return {
                "success": False,
                "outputs": [],
                "message": (
                    "toc_draft.json이 없습니다. "
                    "먼저 'run_toc_planner.py --toc-draft --workspace ...'를 실행하여 "
                    "목차 초안을 생성하고 컨설턴트 승인을 받으세요."
                ),
            }
        if not gate_p15_passed:
            return {
                "success": False,
                "outputs": [],
                "message": (
                    "GATE-P1.5-TO-P2가 아직 승인되지 않았습니다. "
                    "05_planning/toc_draft.json을 검토하고 "
                    "'sustainreport approve P1.5_to_P2 --workspace ...'를 실행하세요."
                ),
            }

    # 이하 기존 blueprint 생성 로직 유지 ...
```

**`_gate_is_passed_local()` 헬퍼 함수** (파일 내에 로컬 정의):

```python
def _gate_is_passed_local(workspace: Path, gate_name: str) -> bool:
    """approval_gates.json에서 해당 게이트의 승인 여부 확인."""
    gates_path = workspace / "approval_gates.json"
    if not gates_path.exists():
        return False
    try:
        data = json.loads(gates_path.read_text(encoding="utf-8"))
        gate = data.get("gates", {}).get(gate_name, {})
        return gate.get("status") == "approved"
    except (json.JSONDecodeError, KeyError):
        return False
```

---

### 작업 5. `_build_toc_draft_prompt()` 헬퍼 함수 추가

```python
def _build_toc_draft_prompt(
    segment_manifest: dict,
    intake_manifest: dict,
) -> str:
    """toc_draft 생성용 LLM 프롬프트 구성."""
    # intake_manifest에서 목차 관련 정보 추출
    a_structure = intake_manifest.get("A_structure", {})
    preferred_toc = a_structure.get("preferred_toc_reference", "")
    scope_inclusions = a_structure.get("scope_inclusions", [])
    scope_exclusions = a_structure.get("scope_exclusions", [])
    priority_sections = a_structure.get("priority_sections", [])

    # 세그먼트 요약 (처음 10개만)
    segments = segment_manifest.get("segments", [])[:10]
    segment_summary = "\n".join(
        f"- [{s.get('segment_id')}] {s.get('heading_path', '(제목 없음)')}"
        for s in segments
    )

    prompt = f"""당신은 ESG 지속가능경영보고서 목차 설계 전문가입니다.

아래 정보를 바탕으로 보고서 목차 초안(toc_draft)을 JSON 형식으로 생성하세요.

## 인테이크 정보
- 참조 목차 스타일: {preferred_toc or '명시 없음'}
- 포함 범위: {', '.join(scope_inclusions) if scope_inclusions else '명시 없음'}
- 제외 범위: {', '.join(scope_exclusions) if scope_exclusions else '명시 없음'}
- 우선 섹션: {', '.join(priority_sections) if priority_sections else '명시 없음'}

## 투입 자료 세그먼트 (일부)
{segment_summary}

## 출력 형식 (JSON)
```json
{{
  "sections": [
    {{
      "section_id": "SEC-1",
      "heading_text": "섹션 제목",
      "level": 1,
      "parent_section_id": null,
      "estimated_pages": 3,
      "frameworks": ["GRI 2-1"],
      "notes": null
    }}
  ]
}}
```

## 주의사항
- section_id는 SEC-N 형식으로 계층을 표현 (예: SEC-1, SEC-1.1, SEC-1.1.1)
- level은 1(장), 2(절), 3(소절), 4(세부항목)
- 증거 없는 섹션에는 notes 필드에 "[자료 부족 — 컨설턴트 확인 필요]" 기재
- 일반적인 ESG 보고서 목차 구조를 따르되, 인테이크 정보를 우선 반영
- 전체 섹션 수는 15~30개 사이로 작성
"""
    return prompt
```

---

### 작업 6. `_parse_toc_draft()` 헬퍼 함수 추가

기존 `_extract_json_object_candidates()` 함수를 재사용하여:

```python
def _parse_toc_draft(raw_content: str) -> dict:
    """LLM 응답에서 toc_draft JSON을 파싱한다."""
    candidates = _extract_json_object_candidates(raw_content)
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if "sections" in data and isinstance(data["sections"], list):
                return data
        except json.JSONDecodeError:
            continue
    raise ValueError(f"toc_draft JSON을 파싱할 수 없습니다. 응답: {raw_content[:300]}")
```

---

### 작업 7. `_record_gate_approved()` 헬퍼 함수 추가

skip-approval 모드에서 approval_gates.json에 직접 approved 상태를 기록한다.
기존 `run_toc_planner.py`에 P2_to_P3 skip-approval 처리 코드가 있으면 해당 패턴을 복사하여 재사용한다.

```python
def _record_gate_approved(workspace: Path, gate_name: str, approver: str = "system") -> None:
    """approval_gates.json에 게이트 approved 상태를 직접 기록한다."""
    gates_path = workspace / "approval_gates.json"

    if gates_path.exists():
        data = json.loads(gates_path.read_text(encoding="utf-8"))
    else:
        data = {"gates": {}}

    data.setdefault("gates", {})[gate_name] = {
        "status": "approved",
        "approved_at": utc_now(),
        "approved_by": approver,
        "gate_name": gate_name,
    }

    gates_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
```

---

## 완료 기준 체크리스트

```bash
# 1. --toc-draft 모드 실행
uv run python scripts/run_toc_planner.py \
  --workspace workspaces/PRJ-2026-KRS-001 \
  --toc-draft \
  --skip-approval

# 2. toc_draft.json 생성 확인
ls -la workspaces/PRJ-2026-KRS-001/05_planning/toc_draft.json
cat workspaces/PRJ-2026-KRS-001/05_planning/toc_draft.json | python3.13 -m json.tool

# 3. toc_draft 미승인 상태에서 기본 모드 실행 시 오류 반환 확인
# (approval_gates.json에서 P1.5_to_P2를 수동으로 waiting으로 바꾼 뒤)
# uv run python scripts/run_toc_planner.py --workspace ... → "GATE-P1.5-TO-P2가 승인되지 않았습니다" 메시지 출력 확인

# 4. skip-approval 모드에서 전체 플로우 확인 (toc_draft + blueprint 연속 실행)
uv run python scripts/run_toc_planner.py \
  --workspace workspaces/PRJ-2026-KRS-001 \
  --skip-approval

# 5. 기존 테스트 회귀 없음 확인
uv run pytest tests/ -x -q
```

---

## 결정 원칙

- `_get_gate_config()` 함수가 이미 run_toc_planner.py에 있으면 그대로 재사용한다.
- `state_manager.wait_for_approval()`의 시그니처는 기존 P2_to_P3 처리 코드를 참고한다.
- LLM 응답 파싱 실패 시 debug artifact를 저장하는 기존 `_save_planning_debug_artifacts()` 패턴을 재사용한다.
- `run_toc_planner.py`의 기존 tests는 구 3-output(structure_index, writing_blueprint, section_manifest)을 테스트한다. 이 테스트는 깨지지 않아야 한다 — 기본 모드(--toc-draft 없이)가 skip_approval=True일 때 toc_draft도 생성하고 이후 blueprint도 생성하도록 기본 모드를 설계하면 기존 테스트 회귀를 방지할 수 있다.
