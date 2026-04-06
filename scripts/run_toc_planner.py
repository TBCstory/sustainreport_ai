#!/usr/bin/env python3.13
"""
run_toc_planner.py — P2 기획 스크립트

역할:
1. segment_manifest.json 읽기
2. toc-planner 에이전트 호출
3. structure_index.json, section_manifest.json, writing_blueprint.json 생성
4. P2→P3 게이트 대기 상태를 approval_gates.json에 기록 후 즉시 반환

사용법:
    python scripts/run_toc_planner.py --workspace /path/to/PRJ-YYYY-CODE-NNN
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import click

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from llm.router import ModelRouter
from scripts.state_manager import StateManager

PLANNING_DEBUG_DIR = Path("05_planning") / "_debug"
MAX_NORMALIZED_DOCS = 5
MAX_NORMALIZED_DOC_CHARS = 4000
MAX_TOTAL_NORMALIZED_DOC_CHARS = 12000


def utc_now() -> str:
    """UTC timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_json_object_candidates(raw_content: str) -> list[str]:
    """응답 텍스트에서 가능한 JSON object 후보를 추출한다."""
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(candidate: str) -> None:
        normalized = candidate.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            candidates.append(normalized)

    stripped = raw_content.strip()
    if stripped:
        _add(stripped)

    for match in re.finditer(r"```(?:json)?\s*(.*?)```", raw_content, re.DOTALL | re.IGNORECASE):
        _add(match.group(1))

    depth = 0
    start_idx: Optional[int] = None
    in_string = False
    escape = False

    for idx, char in enumerate(raw_content):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            if depth == 0:
                start_idx = idx
            depth += 1
            continue

        if char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start_idx is not None:
                _add(raw_content[start_idx : idx + 1])
                start_idx = None

    return candidates


def parse_planning_bundle(raw_content: str) -> dict[str, dict[str, Any]]:
    """
    LLM이 반환한 planning bundle을 파싱하여 3개 파일로 분리한다.

    Args:
        raw_content: LLM이 반환한 원본 텍스트 (JSON 또는 Markdown 코드 블록)

    Returns:
        {"structure_index": {...}, "writing_blueprint": {...}, "section_manifest": {...}}

    Raises:
        ValueError: 필수 키가 없거나 파싱 실패 시
    """
    if not raw_content or not raw_content.strip():
        raise ValueError(
            "Planning bundle response was empty. Expected one JSON object with "
            "'structure_index', 'writing_blueprint', and 'section_manifest'."
        )

    required_keys = ["structure_index", "writing_blueprint", "section_manifest"]
    errors: list[str] = []

    for candidate in _extract_json_object_candidates(raw_content):
        try:
            bundle = json.loads(candidate)
        except json.JSONDecodeError as e:
            errors.append(f"JSON decode error at line {e.lineno}, column {e.colno}: {e.msg}")
            continue

        if not isinstance(bundle, dict):
            errors.append("Planning bundle must be a JSON object.")
            continue

        missing = [k for k in required_keys if k not in bundle]
        if missing:
            errors.append(f"Planning bundle missing required keys: {missing}")
            continue

        return {
            "structure_index": bundle["structure_index"],
            "writing_blueprint": bundle["writing_blueprint"],
            "section_manifest": bundle["section_manifest"],
        }

    if not errors:
        raise ValueError(
            "Planning bundle response did not contain a JSON object. Expected one JSON object with "
            "'structure_index', 'writing_blueprint', and 'section_manifest'."
        )

    raise ValueError("Unable to parse planning bundle response. " + " | ".join(errors[:3]))


def _load_json_file(path: Path) -> Any:
    """JSON 파일을 로드한다."""
    return json.loads(path.read_text(encoding="utf-8"))


def _load_guidance_file(workspace: Path, filename: str) -> Any:
    """workspace guidance 우선, 없으면 project-level guidance fallback."""
    workspace_path = workspace / "guidance" / filename
    if workspace_path.exists():
        return _load_json_file(workspace_path)

    project_path = PROJECT_ROOT / "guidance" / filename
    if project_path.exists():
        return _load_json_file(project_path)

    raise FileNotFoundError(f"Required guidance file not found: {filename}")


def _load_normalized_document_snapshots(workspace: Path) -> list[dict[str, Any]]:
    """planner prompt에 넣을 정규화 문서 스냅샷을 제한적으로 로드한다."""
    docs_dir = workspace / "03_normalized_md"
    snapshots: list[dict[str, Any]] = []
    total_chars = 0

    if not docs_dir.exists():
        return snapshots

    for path in sorted(docs_dir.glob("*.md")):
        if len(snapshots) >= MAX_NORMALIZED_DOCS or total_chars >= MAX_TOTAL_NORMALIZED_DOC_CHARS:
            break

        content = path.read_text(encoding="utf-8")
        truncated = False

        if len(content) > MAX_NORMALIZED_DOC_CHARS:
            content = content[:MAX_NORMALIZED_DOC_CHARS]
            truncated = True

        remaining = MAX_TOTAL_NORMALIZED_DOC_CHARS - total_chars
        if len(content) > remaining:
            content = content[:remaining]
            truncated = True

        if not content:
            continue

        snapshots.append(
            {
                "path": str(path.relative_to(workspace)),
                "content": content,
                "truncated": truncated,
            }
        )
        total_chars += len(content)

    return snapshots


def _build_planning_prompt(workspace: Path, segment_manifest_path: Path) -> str:
    """live planner 호출용 프롬프트를 조립한다."""
    prompt_template = _load_agent_prompt("toc-planner").replace("{workspace}", str(workspace))

    context: dict[str, Any] = {
        "phase": "P2",
        "workspace": str(workspace),
        "project_id": workspace.name,
        "segment_manifest_path": str(segment_manifest_path.relative_to(workspace)),
    }

    prompt = prompt_template
    for key, value in context.items():
        placeholder = f"{{{{{key}}}}}"
        value_str = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        prompt = prompt.replace(placeholder, value_str)

    file_registry_path = workspace / "02_file_registry" / "file_registry.json"
    runtime_context = {
        "project_id": workspace.name,
        "workspace_path": str(workspace),
        "file_registry": _load_json_file(file_registry_path),
        "segment_manifest": _load_json_file(segment_manifest_path),
        "normalized_documents": _load_normalized_document_snapshots(workspace),
        "style_guide": _load_guidance_file(workspace, "style_guide.json"),
        "terminology_dictionary": _load_guidance_file(workspace, "terminology_dictionary.json"),
    }

    runtime_guidance = """
## Runtime Execution Context

이 실행에서는 파일시스템 직접 접근이 불가능하다. 아래 JSON/markdown 스냅샷을 이미 읽은 authoritative input으로 간주하라.

- `project_id`는 반드시 runtime context의 값을 그대로 사용한다.
- 입력 증거가 희박해도 가용 근거를 바탕으로 **보수적이지만 유효한** planning bundle을 생성한다.
- 추가 파일 요청, 사과문, `_requires_input`, `_required_action` 같은 상태 보고용 필드는 출력하지 않는다.
- 출력은 최상위 키 `structure_index`, `writing_blueprint`, `section_manifest`를 가진 raw JSON object 하나만 반환한다.
""".strip()

    prompt = (
        prompt.rstrip()
        + "\n\n"
        + runtime_guidance
        + "\n\n```json\n"
        + json.dumps(runtime_context, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    return prompt


def _call_toc_planner(prompt: str, router: ModelRouter) -> dict[str, Any]:
    """조립된 프롬프트로 toc-planner를 호출한다."""
    messages = [{"role": "user", "content": prompt}]
    return router.complete_messages(messages=messages, agent="toc-planner")


def _validate_planning_bundle(bundle: dict[str, dict[str, Any]]) -> None:
    """planning bundle이 downstream smoke에 필요한 최소 shape를 갖추었는지 확인한다."""
    structure_entries = bundle.get("structure_index", {}).get("entries", [])
    blueprint_sections = bundle.get("writing_blueprint", {}).get("sections", [])
    manifest_sections = bundle.get("section_manifest", {}).get("sections", [])

    if not structure_entries:
        raise ValueError("Planning bundle contained an empty structure_index.entries list.")
    if not blueprint_sections:
        raise ValueError("Planning bundle contained an empty writing_blueprint.sections list.")
    if not manifest_sections:
        raise ValueError("Planning bundle contained an empty section_manifest.sections list.")


def _normalize_planning_bundle(bundle: dict[str, dict[str, Any]], project_id: str) -> dict[str, dict[str, Any]]:
    """workspace-level canonical fields를 보정한다."""
    normalized = {
        "structure_index": dict(bundle["structure_index"]),
        "writing_blueprint": dict(bundle["writing_blueprint"]),
        "section_manifest": dict(bundle["section_manifest"]),
    }
    normalized["structure_index"]["project_id"] = project_id
    normalized["writing_blueprint"]["project_id"] = project_id
    normalized["section_manifest"]["project_id"] = project_id
    normalized["writing_blueprint"]["approved"] = False
    normalized["writing_blueprint"]["approved_at"] = None
    return normalized


def _save_planning_debug_artifacts(
    workspace: Path,
    prompt: str,
    failure_stage: str,
    error: str,
    raw_content: Optional[str] = None,
    llm_result: Optional[dict[str, Any]] = None,
) -> list[str]:
    """run-plan 실패 시 디버그 가능한 prompt/raw/failure context를 저장한다."""
    debug_dir = workspace / PLANNING_DEBUG_DIR
    debug_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[str] = []

    prompt_path = debug_dir / "toc_planner_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    outputs.append(str(prompt_path.relative_to(workspace)))

    failure_payload: dict[str, Any] = {
        "failure_stage": failure_stage,
        "error": error,
        "saved_at": utc_now(),
        "model": llm_result.get("model") if llm_result else None,
        "run_id": llm_result.get("run_id") if llm_result else None,
    }

    if raw_content is not None:
        raw_path = debug_dir / "toc_planner_raw_response.txt"
        raw_path.write_text(raw_content, encoding="utf-8")
        outputs.append(str(raw_path.relative_to(workspace)))
        candidates = _extract_json_object_candidates(raw_content)
        failure_payload["raw_response_length"] = len(raw_content)
        failure_payload["json_candidate_count"] = len(candidates)
        failure_payload["json_candidate_previews"] = [candidate[:200] for candidate in candidates[:3]]

    failure_path = debug_dir / "toc_planner_failure.json"
    failure_path.write_text(json.dumps(failure_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    outputs.append(str(failure_path.relative_to(workspace)))

    return outputs


def _load_agent_prompt(agent_name: str) -> str:
    """에이전트 프롬프트를 로드한다."""
    agent_dir = PROJECT_ROOT / "agents"
    prompt_path = agent_dir / f"{agent_name}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Agent prompt not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def _get_gate_config(gate_name: str) -> dict[str, Any]:
    """gate_rules.json에서 게이트 설정을 로드한다."""
    gate_rules_path = PROJECT_ROOT / "orchestration" / "gate_rules.json"
    if gate_rules_path.exists():
        gate_rules = json.loads(gate_rules_path.read_text(encoding="utf-8"))
        return gate_rules.get("gates", {}).get(gate_name, {})
    return {}


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


def _build_toc_draft_prompt(
    segment_manifest: dict,
    intake_manifest: dict,
) -> str:
    """toc_draft 생성용 LLM 프롬프트 구성."""
    a_structure = intake_manifest.get("A_structure", {})
    # PKT-B003: 정규 키 우선, alias fallback (1릴리스 호환)
    preferred_toc = a_structure.get("custom_toc_reference") or a_structure.get("preferred_toc_reference", "")
    scope_inclusions = a_structure.get("scope_inclusions", [])
    scope_exclusions = a_structure.get("scope_exclusions", [])
    priority_sections = a_structure.get("section_priority") or a_structure.get("priority_sections", [])

    segments = segment_manifest.get("segments", [])[:10]
    segment_summary = "\n".join(f"- [{s.get('segment_id')}] {s.get('heading_path', '(제목 없음)')}" for s in segments)

    prompt = f"""당신은 ESG 지속가능경영보고서 목차 설계 전문가입니다.

아래 정보를 바탕으로 보고서 목차 초안(toc_draft)을 JSON 형식으로 생성하세요.

## 인테이크 정보
- 참조 목차 스타일: {preferred_toc or "명시 없음"}
- 포함 범위: {", ".join(scope_inclusions) if scope_inclusions else "명시 없음"}
- 제외 범위: {", ".join(scope_exclusions) if scope_exclusions else "명시 없음"}
- 우선 섹션: {", ".join(priority_sections) if priority_sections else "명시 없음"}

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


def run_toc_draft(
    workspace: str | Path,
    skip_approval: bool = False,
    state_manager=None,
) -> dict:
    """
    P1.5: 목차 초안(toc_draft.json) 생성 후 컨설턴트 승인 대기.

    반환:
        {
            "success": bool,
            "outputs": list[str],
            "message": str,
            "waiting": bool,
            "gate_name": str,
            "gate_status": str,
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

    intake_manifest_path = workspace / "00_definition" / "intake_manifest.json"
    intake_manifest = {}
    if intake_manifest_path.exists():
        with open(intake_manifest_path, encoding="utf-8") as f:
            intake_manifest = json.load(f)

    # ── 2. LLM 프롬프트 구성 ──
    toc_prompt = _build_toc_draft_prompt(segment_manifest, intake_manifest)

    # ── 3. LLM 호출 ──
    router = ModelRouter()
    llm_result = router.complete_messages(
        messages=[{"role": "user", "content": toc_prompt}],
        agent="toc-planner",
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
        toc_output["status"] = "approved"
        toc_output["approved_at"] = utc_now()
        toc_output["approved_by"] = "skip_approval"
        toc_draft_path.write_text(
            json.dumps(toc_output, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _record_gate_approved(workspace, gate_name, approver="skip_approval")

        return {
            "success": True,
            "outputs": outputs,
            "message": "P1.5 완료 (skip-approval 모드: toc_draft 자동 승인됨).",
            "waiting": False,
            "gate_name": gate_name,
            "gate_status": "skipped",
        }


def run_toc_planner(
    workspace: str | Path,
    state_manager=None,
    skip_approval: bool = False,
) -> dict:
    """
    P2: 기획 단계를 실행한다.

    Args:
        workspace: 워크스페이스 경로
        skip_approval: True면 P2→P3 게이트 승인을 건너뜀 (테스트용)

    Returns:
        {"success": bool, "outputs": list[str], "message": str}
    """
    workspace = Path(workspace)
    state_manager = state_manager or StateManager(workspace)

    outputs = []

    # ── P1.5-TO-P2 게이트 통과 여부 확인 ──
    toc_draft_path = workspace / "05_planning" / "toc_draft.json"

    if not skip_approval:
        gate_p15_passed = _gate_is_passed_local(workspace, "P1.5_to_P2")
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
    # else: skip-approval 모드 — P1.5_TO_P2 게이트 자동 통과 (toc_draft 존재 불필요)

    # 1. segment_manifest.json 존재 확인
    segment_manifest_path = workspace / "04_segments" / "segment_manifest.json"
    if not segment_manifest_path.exists():
        return {
            "success": False,
            "outputs": [],
            "message": f"segment_manifest.json not found: {segment_manifest_path}",
        }

    # 2. ModelRouter 생성 (LLM 직접 호출용)
    router = ModelRouter()

    # 3. prompt 조립
    try:
        prompt = _build_planning_prompt(
            workspace=workspace,
            segment_manifest_path=segment_manifest_path,
        )
    except Exception as e:
        return {
            "success": False,
            "outputs": [],
            "message": f"Failed to prepare planning prompt: {e}",
        }

    # 4. LLM 호출
    try:
        llm_result = _call_toc_planner(prompt=prompt, router=router)
    except Exception as e:
        debug_outputs = _save_planning_debug_artifacts(
            workspace=workspace,
            prompt=prompt,
            failure_stage="llm_call",
            error=str(e),
        )
        return {
            "success": False,
            "outputs": debug_outputs,
            "message": f"Failed to generate planning bundle: {e}. Debug artifacts saved: {debug_outputs}",
        }

    # 5. planning bundle 파싱/검증
    raw_content = llm_result.get("content") or ""
    try:
        planning_bundle = parse_planning_bundle(raw_content)
        _validate_planning_bundle(planning_bundle)
        planning_bundle = _normalize_planning_bundle(planning_bundle, workspace.name)
    except Exception as e:
        failure_stage = "prompt_contract" if "empty " in str(e).lower() else "parse"
        debug_outputs = _save_planning_debug_artifacts(
            workspace=workspace,
            prompt=prompt,
            failure_stage=failure_stage,
            error=str(e),
            raw_content=raw_content,
            llm_result=llm_result,
        )
        return {
            "success": False,
            "outputs": debug_outputs,
            "message": f"Failed to generate planning bundle: {e}. Debug artifacts saved: {debug_outputs}",
        }

    # 6. 출력 파일 저장 (approval 대기 전에도 산출물이 남아 있어야 함)
    output_map = {
        "05_planning/structure_index.json": planning_bundle["structure_index"],
        "05_planning/writing_blueprint.json": planning_bundle["writing_blueprint"],
        "05_planning/section_manifest.json": planning_bundle["section_manifest"],
    }

    for file_path, content in output_map.items():
        full_path = workspace / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        outputs.append(file_path)

    # 7. 상태 업데이트 (phase status로 P2 완료를 기록)
    state_manager.set_phase_status("P2", "complete")
    state_manager.sync()

    # 8. 이벤트 로깅
    _log_milestone(workspace, "P2策划完成", llm_result.get("run_id"))

    # 9. P2→P3 게이트는 산출물 저장 후 대기한다.
    gate_name = "P2_to_P3"
    if not skip_approval:
        gate_config = _get_gate_config(gate_name)
        required_approvers = gate_config.get("required_approvers", [])

        state_manager.wait_for_approval(
            gate_name=gate_name,
            required_approvers=required_approvers,
            requester="run_toc_planner",
        )
        state_manager.sync()

        # 즉시 반환: 승인 대기 상태를 approval_gates.json에 기록 후结束的
        # 승인은 별도의 cmd_approve_blueprint 또는 CLI 도구로 처리
        return {
            "success": True,
            "outputs": outputs,
            "message": (
                f"P2 completed. Blueprint ready for review. "
                f"Gate '{gate_name}' is waiting for approval. "
                f"Use 'sustainreport approve P2_to_P3 --workspace ...' or edit approval_gates.json directly."
            ),
            "waiting": True,
            "gate_name": gate_name,
            "gate_status": "waiting",
        }
    else:
        # skip-approval 모드: blueprint approved 플래그 + 게이트 approved 상태를 모두 기록한다.
        # _check_blueprint_approved()가 writing_blueprint.json의 approved 필드를 확인하고,
        # _gate_is_passed()가 approval_gates.json의 status=="approved"를 확인하므로
        # 두 곳 모두를 갱신해야 상태 명령이 정면충돌하지 않는다.
        bp_path = workspace / "05_planning" / "writing_blueprint.json"
        if bp_path.exists():
            bp = json.loads(bp_path.read_text(encoding="utf-8"))
            bp["approved"] = True
            bp["approved_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            bp_path.write_text(json.dumps(bp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        # Directly write the approved gate entry to bypass the wait->poll flow.
        # record_approval() leaves status=waiting when required approvers aren't satisfied,
        # which would cause _gate_is_passed() to return False even after recording.
        approval_gates_path = workspace / "approval_gates.json"
        if approval_gates_path.exists():
            approval_data = json.loads(approval_gates_path.read_text(encoding="utf-8"))
        else:
            approval_data = {"gates": {}, "project_id": workspace.name}

        decided_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        approval_data.setdefault("gates", {})[gate_name] = {
            "gate_name": gate_name,
            "approval_type": "human",
            "required_approvers": ["project_manager", "consultant_lead"],
            "current_approvers": [
                {
                    "approver": "automation",
                    "signature": "skip-approval",
                    "decided_at": decided_at,
                    "notes": "Automated approval via --skip-approval flag",
                }
            ],
            "status": "approved",
            "decision": "approved",
            "decided_at": decided_at,
            "decided_by": "automation",
            "requested_at": approval_data.get("gates", {}).get(gate_name, {}).get("requested_at", decided_at),
            "requested_by": "run_toc_planner",
        }
        approval_gates_path.write_text(json.dumps(approval_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        # Keep state_manager's in-memory _approval_gates in sync so that
        # the caller's sync() call does not overwrite our direct write.
        state_manager._approval_gates = approval_data

    return {
        "success": True,
        "outputs": outputs,
        "message": f"P2 completed: {len(outputs)} files generated",
        "gate_status": "approved",
    }


def _log_milestone(workspace: Path, message: str, run_id: Optional[str] = None) -> None:
    """마일스톤 이벤트 로깅."""
    try:
        from scripts.log_event import log_milestone

        bus_dir = workspace / "context_bus"
        bus_dir.mkdir(parents=True, exist_ok=True)
        log_milestone(
            message=message,
            phase="P2",
            section=None,
            run_id=run_id or "unknown",
            bus_dir=bus_dir,
        )
    except Exception:
        pass  # 로깅 실패해도主线 影响 안 받음


# ─────────────────────────────────────────────────────────────────────────────
# CLI 진입점
# ─────────────────────────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--workspace",
    "-w",
    "workspace",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="워크스페이스 경로",
)
@click.option(
    "--skip-approval",
    is_flag=True,
    default=False,
    help="P2→P3 게이트 승인 건너뛰기 (테스트용)",
)
@click.option(
    "--toc-draft",
    "toc_draft_only",
    is_flag=True,
    default=False,
    help="P1.5 모드: toc_draft.json만 생성하고 GATE-P1.5-TO-P2 대기 상태를 기록한다.",
)
def main(workspace: Path, skip_approval: bool, toc_draft_only: bool) -> int:
    """P2 기획 실행."""
    print(f"[run_toc_planner] Starting P2 planning...")
    print(f"  workspace: {workspace}")
    print(f"  skip_approval: {skip_approval}")
    print(f"  toc_draft_only: {toc_draft_only}")

    if toc_draft_only:
        result = run_toc_draft(workspace=str(workspace), skip_approval=skip_approval)
    else:
        result = run_toc_planner(workspace=str(workspace), skip_approval=skip_approval)

    if result["success"]:
        print(f"\n✅ P2 completed successfully")
        print(f"   Outputs: {result['outputs']}")
        print(f"   Message: {result['message']}")
        return 0
    else:
        print(f"\n❌ P2 failed")
        print(f"   Message: {result['message']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
