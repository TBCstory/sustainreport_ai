#!/usr/bin/env python3.13
"""
dispatch_agent.py — 에이전트 프롬프트 로드 + LLM 호출 + 출력 쓰기 추상화

역할:
1. 에이전트 프롬프트 로드 (agents/{agent}.md)
2. 컨텍스트 조립 ({workspace} 치환, events.jsonl 참조)
3. LLM 호출 (llm/router.py 사용)
4. 출력 파일 쓰기
5. 게이트 승인 대기 핸들링

사용법:
    from scripts.dispatch_agent import AgentDispatcher
    dispatcher = AgentDispatcher("/path/to/PRJ-YYYY-CODE-NNN")
    result = dispatcher.dispatch(
        agent="toc-planner",
        context={"custom_key": "value"},
        output_files=["05_planning/structure_index.json"],
    )
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from llm.router import LLMCallError, ModelRouter

# ─────────────────────────────────────────────────────────────────────────────
# 경로 상수
# ─────────────────────────────────────────────────────────────────────────────

AGENTS_DIR = PROJECT_ROOT / "agents"
LLM_CALL_LOG = "llm/call_log.jsonl"

# ─────────────────────────────────────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DispatchResult:
    """에이전트 디스패치 결과."""

    success: bool
    agent: str
    output_files: list[str] = field(default_factory=list)
    content: Optional[str] = None
    error: Optional[str] = None
    run_id: Optional[str] = None
    latency_ms: float = 0.0
    model: Optional[str] = None


@dataclass
class LLMResult:
    """LLM 호출 결과."""

    content: str
    model: str
    usage: dict
    latency_ms: float
    run_id: str


# ─────────────────────────────────────────────────────────────────────────────
# 예외
# ─────────────────────────────────────────────────────────────────────────────


class DispatchError(Exception):
    """디스패치 실패."""

    pass


class AgentPromptNotFoundError(DispatchError):
    """에이전트 프롬프트 파일을 찾을 수 없음."""

    pass


class OutputWriteError(DispatchError):
    """출력 파일 쓰기 실패."""

    pass


# ─────────────────────────────────────────────────────────────────────────────
# AgentDispatcher
# ─────────────────────────────────────────────────────────────────────────────


class AgentDispatcher:
    """
    에이전트 호출을统一 처리하는 디스패처.

    Responsibilities:
    - 에이전트 프롬프트 로드 + 플레이스홀더 치환
    - 컨텍스트 조립 (events.jsonl recent entries)
    - LLM 호출 (ModelRouter.complete_messages)
    - 출력 파일 쓰기
    - 상태 동기화
    """

    def __init__(
        self,
        workspace: str | Path,
        state_manager: Optional[Any] = None,
        router: Optional[ModelRouter] = None,
    ):
        self.workspace = Path(workspace)
        self.state_manager = state_manager
        self.router = router or ModelRouter()

        # Recent events cache (loaded lazily)
        self._recent_events: Optional[list[dict]] = None

    # ─────────────────────────────────────────────────────────────────────────
    # HD-3: 빈 응답 감지
    # ─────────────────────────────────────────────────────────────────────────

    EMPTY_RESPONSE_PATTERNS = [
        "대기 상태",
        "대기중",
        "waiting for",
        "no content available",
        "아직 작성되지 않았습니다",
    ]

    def _is_empty_or_waiting_response(self, text: str) -> bool:
        """LLM 응답이 실질적 내용 없는 대기/빈 응답인지 판별."""
        stripped = text.strip()
        text_lower = stripped.lower()
        for pattern in self.EMPTY_RESPONSE_PATTERNS:
            if pattern in text_lower:
                return True
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # 공개 API
    # ─────────────────────────────────────────────────────────────────────────

    def dispatch(
        self,
        agent: str,
        context: Optional[dict[str, Any]] = None,
        output_files: Optional[list[str]] = None,
        wait_for_approval: bool = False,
        gate_name: Optional[str] = None,
        section_id: Optional[str] = None,
        extra_system_prompt: Optional[str] = None,
    ) -> DispatchResult:
        """
        에이전트를 디스패치하고 결과를 반환한다.

        Args:
            agent: 에이전트 이름 (e.g., "data-analyst", "toc-planner")
            context: 추가 컨텍스트 키-값
            output_files: 생성해야 할 출력 파일 경로 리스트 (workspace 상대경로)
            wait_for_approval: True면 게이트 승인을 기다림
            gate_name: 게이트 ID (wait_for_approval True 시必需)
            section_id: 섹션 ID (선택, 로깅용)
            extra_system_prompt: 시스템 프롬프트에 추가할 내용

        Returns:
            DispatchResult
        """
        output_files = output_files or []
        context = context or {}

        # Run 시작
        run_id = self._start_run(agent, section_id)

        try:
            # 1. 프롬프트 로드
            prompt = self._load_agent_prompt(agent)
            if not prompt:
                raise AgentPromptNotFoundError(f"Prompt not found for agent: {agent}")

            # 2. 컨텍스트 조립
            full_prompt = self._build_context(prompt, context, extra_system_prompt)

            # 3. 게이트 승인 대기 (필요시)
            if wait_for_approval and gate_name:
                approved = self._wait_for_human_approval(gate_name)
                if not approved:
                    return DispatchResult(
                        success=False,
                        agent=agent,
                        output_files=output_files,
                        error=f"Gate '{gate_name}' rejected or timed out",
                        run_id=run_id,
                    )

            # 4. LLM 호출
            llm_result = self._call_llm(full_prompt, agent)

            # HD-3: 빈 응답 감지 → 1회 재시도
            if self._is_empty_or_waiting_response(llm_result.content):
                llm_result = self._call_llm(full_prompt, agent)
                if self._is_empty_or_waiting_response(llm_result.content):
                    return DispatchResult(
                        success=False,
                        agent=agent,
                        output_files=output_files,
                        error="LLM returned empty/waiting response after retry",
                        run_id=run_id,
                    )

            # 5. 출력 파일 쓰기
            if output_files:
                self._write_outputs(llm_result.content, output_files)

            # 6. 상태 동기화
            self._sync_state(agent, section_id)

            return DispatchResult(
                success=True,
                agent=agent,
                output_files=output_files,
                content=llm_result.content,
                run_id=llm_result.run_id,
                latency_ms=llm_result.latency_ms,
                model=llm_result.model,
            )

        except Exception as e:
            # 예외 발생 시 blocking issue 추가
            if self.state_manager:
                self.state_manager.add_blocking_issue(
                    issue={
                        "reason": f"Agent '{agent}' dispatch failed: {str(e)}",
                        "severity": "high",
                        "section_id": section_id,
                    },
                    agent=agent,
                    phase=context.get("phase") if context else None,
                )
                self.state_manager.sync()

            return DispatchResult(
                success=False,
                agent=agent,
                output_files=output_files,
                error=str(e),
                run_id=run_id,
            )

    # ─────────────────────────────────────────────────────────────────────────
    # 내부 메서드: 프롬프트 로드
    # ─────────────────────────────────────────────────────────────────────────

    def _load_agent_prompt(self, agent: str) -> str:
        """agents/{agent}.md 파일을 로드."""
        prompt_path = AGENTS_DIR / f"{agent}.md"
        if not prompt_path.exists():
            raise AgentPromptNotFoundError(f"Agent prompt not found: {prompt_path}")

        content = prompt_path.read_text(encoding="utf-8")

        # {workspace} 플레이스홀더 치환
        content = content.replace("{workspace}", str(self.workspace))

        return content

    # ─────────────────────────────────────────────────────────────────────────
    # 내부 메서드: 컨텍스트 조립
    # ─────────────────────────────────────────────────────────────────────────

    def _build_context(
        self,
        base_prompt: str,
        extra_context: dict[str, Any],
        extra_system_prompt: Optional[str],
    ) -> str:
        """
        기본 프롬프트에 추가 컨텍스트를 결합한다.

        1. extra_context의 키-값을 {{key}} 플레이스홀더로 치환
        2. recent events를 프롬프트 끝에 추가
        3. extra_system_prompt 추가
        """
        prompt = base_prompt

        # 1. extra_context 플레이스홀더 치환
        for key, value in extra_context.items():
            placeholder = f"{{{{{key}}}}}"
            value_str = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
            prompt = prompt.replace(placeholder, value_str)

        # 2. recent events 추가
        recent_events = self._get_recent_events(limit=10)
        if recent_events:
            events_text = self._format_recent_events(recent_events)
            prompt = prompt.rstrip() + "\n\n" + events_text

        # 3. extra_system_prompt 추가
        if extra_system_prompt:
            prompt = prompt.rstrip() + "\n\n" + extra_system_prompt

        return prompt

    def _get_recent_events(self, limit: int = 10) -> list[dict]:
        """context_bus/events.jsonl에서 최근 이벤트를 로드."""
        if self._recent_events is not None:
            return self._recent_events[-limit:]

        events_file = self.workspace / "context_bus" / "events.jsonl"
        if not events_file.exists():
            self._recent_events = []
            return []

        try:
            events = []
            with open(events_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            self._recent_events = events[-limit:]
            return self._recent_events
        except (OSError, IOError):
            self._recent_events = []
            return []

    def _format_recent_events(self, events: list[dict]) -> str:
        """이벤트 리스트를 프롬프트에 삽입할 텍스트로 포맷."""
        if not events:
            return ""

        lines = ["\n--- 최근 컨텍스트 이벤트 (참고용) ---\n"]
        for ev in events[-10:]:  # 최대 10개
            ts = ev.get("timestamp", "?")
            ev_type = ev.get("type", "?")
            msg = ev.get("message", "")
            agent = ev.get("agent", "")
            phase = ev.get("phase", "")

            header = f"[{ts}] {ev_type}"
            if agent:
                header += f" | agent={agent}"
            if phase:
                header += f" | phase={phase}"

            lines.append(header)
            if msg:
                lines.append(f"  {msg[:200]}")  # 200자 제한

        lines.append("---\n")
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────────
    # 내부 메서드: LLM 호출
    # ─────────────────────────────────────────────────────────────────────────

    def _call_llm(self, prompt: str, agent: str) -> LLMResult:
        """ModelRouter를 사용하여 LLM 호출 수행."""
        messages = [{"role": "user", "content": prompt}]

        try:
            result = self.router.complete_messages(messages=messages, agent=agent)

            return LLMResult(
                content=result["content"],
                model=result["model"],
                usage=result.get("usage", {}),
                latency_ms=result.get("latency_ms", 0.0),
                run_id=result.get("run_id", "UNKNOWN"),
            )

        except LLMCallError as e:
            raise DispatchError(f"LLM call failed for agent '{agent}': {e}") from e

    # ─────────────────────────────────────────────────────────────────────────
    # 내부 메서드: 출력 쓰기
    # ─────────────────────────────────────────────────────────────────────────

    def _write_outputs(self, content: str, output_files: list[str]) -> None:
        """
        LLM 결과를 output_files에 쓴다.

        Rules:
        - 디렉토리가 없으면 자동 생성
        - Markdown 내 JSON code block에서 JSON 추출 시도
        - JSON으로 파싱 가능한 경우 Pretty-print
        - 그렇지 않으면 마크다운/일반 텍스트로 저장
        """
        for file_path in output_files:
            full_path = self.workspace / file_path
            try:
                # 디렉토리 자동 생성
                full_path.parent.mkdir(parents=True, exist_ok=True)

                # Markdown에서 JSON code block 추출 시도
                json_content = self._extract_json_from_markdown(content)

                # JSON 파싱 시도
                try:
                    parsed = json.loads(json_content)
                    # 여러 JSON 블록이 있을 수 있으므로 첫 번째만 사용
                    if isinstance(parsed, (dict, list)):
                        output_content = json.dumps(parsed, ensure_ascii=False, indent=2)
                    else:
                        output_content = content
                except json.JSONDecodeError:
                    output_content = content

                full_path.write_text(output_content, encoding="utf-8")

            except OSError as e:
                raise OutputWriteError(f"Failed to write output file '{file_path}': {e}") from e

    def _extract_json_from_markdown(self, content: str) -> str:
        """
        Markdown 내 JSON code block에서 JSON 내용을 추출한다.

        ```json
        {...}
        ```
        형태의 블록이 있으면 그 안의 내용만 반환.
        없으면 원본 content 반환.
        """
        # ```json ... ``` 패턴 추출
        match = re.search(r"```json\s*\n(.*?)\n```", content, re.DOTALL)
        if match:
            return match.group(1).strip()
        # ``` ... ``` (json 태그 없이)
        match = re.search(r"```\s*\n(.*?)\n```", content, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
            # JSON으로 파싱 가능한지 확인
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass
        return content

    # ─────────────────────────────────────────────────────────────────────────
    # 내부 메서드: 게이트 승인 대기
    # ─────────────────────────────────────────────────────────────────────────

    def _wait_for_human_approval(self, gate_name: str) -> bool:
        """
        게이트 승인을 기다린다.

        현재는 CLI 기반 폴링 구현.
        approval_gates.json의 상태를 확인하여 승인 여부 판정.

        Returns:
            True: 승인됨
            False: 거부 또는 타임아웃
        """
        if not self.state_manager:
            # state_manager 없으면 승인으로 간주 (PoC 모드)
            return True

        # 승인 대기 상태 설정 - gate_rules.json을 직접 로드
        import json as _json

        gate_rules_path = PROJECT_ROOT / "orchestration" / "gate_rules.json"
        gate_rules = {}
        if gate_rules_path.exists():
            gate_rules = _json.loads(gate_rules_path.read_text(encoding="utf-8"))
        gate_config = gate_rules.get("gates", {}).get(gate_name, {})
        required_approvers = gate_config.get("required_approvers", [])

        self.state_manager.wait_for_approval(
            gate_name=gate_name,
            required_approvers=required_approvers,
            requester="dispatch_agent",
        )

        # 폴링 (최대 5분, 10초 간격)
        max_wait = 300  # 5분
        interval = 10
        elapsed = 0

        print(f"[dispatch_agent] Waiting for approval on gate '{gate_name}'...")
        print(f"[dispatch_agent] Required approvers: {required_approvers}")
        print(f"[dispatch_agent] Approval file: {self.workspace / 'approval_gates.json'}")
        print(f"[dispatch_agent] Polling every {interval}s, max {max_wait}s...")

        while elapsed < max_wait:
            time.sleep(interval)
            elapsed += interval

            # approval_gates.json 다시 로드
            approval_file = self.workspace / "approval_gates.json"
            if approval_file.exists():
                try:
                    data = json.loads(approval_file.read_text(encoding="utf-8"))
                    gate_entry = data.get("gates", {}).get(gate_name, {})
                    status = gate_entry.get("status")
                    if status == "approved":
                        print(f"[dispatch_agent] Gate '{gate_name}' APPROVED")
                        return True
                    if status == "rejected":
                        print(f"[dispatch_agent] Gate '{gate_name}' REJECTED")
                        return False
                except json.JSONDecodeError:
                    pass

            remaining = max_wait - elapsed
            if remaining > 0:
                print(f"[dispatch_agent] Still waiting... ({remaining}s remaining)")

        print(f"[dispatch_agent] Gate '{gate_name}' TIMED OUT after {max_wait}s")
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # 내부 메서드: Run 관리
    # ─────────────────────────────────────────────────────────────────────────

    def _start_run(self, agent: str, section_id: Optional[str]) -> str:
        """새 실행(run)을 시작하고 run_id 반환."""
        if self.state_manager:
            return self.state_manager.create_run(agent=agent, phase="", sections=[section_id] if section_id else [])

        # state_manager 없으면 utils 사용
        from scripts.utils import generate_run_id

        return generate_run_id()

    def _end_run(self, run_id: str, success: bool) -> None:
        """실행(run)을 종료 처리."""
        if self.state_manager:
            outcome = "success" if success else "failed"
            self.state_manager.close_run(run_id, outcome=outcome)

    # ─────────────────────────────────────────────────────────────────────────
    # 내부 메서드: 상태 동기화
    # ─────────────────────────────────────────────────────────────────────────

    def _sync_state(self, agent: str, section_id: Optional[str]) -> None:
        """작업 완료 후 상태 동기화."""
        if self.state_manager:
            self.state_manager.sync()
        # log_event 호출은 각 Phase 실행 래퍼에서 수행


# ─────────────────────────────────────────────────────────────────────────────
# CLI 진입점
# ─────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="에이전트 디스패치 CLI")
    parser.add_argument("workspace", help="워크스페이스 경로")
    parser.add_argument("agent", help="에이전트 이름")
    parser.add_argument("--output", "-o", nargs="+", help="출력 파일 목록")
    parser.add_argument("--context", "-c", help="추가 컨텍스트 (JSON 문자열)")
    parser.add_argument("--wait-approval", "-w", help="게이트 이름", default=None)
    parser.add_argument("--section", "-s", help="섹션 ID", default=None)
    parser.add_argument("--extra-prompt", "-e", help="추가 시스템 프롬프트", default=None)

    args = parser.parse_args()

    # 컨텍스트 파싱
    extra_context = {}
    if args.context:
        try:
            extra_context = json.loads(args.context)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --context: {e}", file=sys.stderr)
            sys.exit(1)

    # 디스패치
    dispatcher = AgentDispatcher(args.workspace)

    result = dispatcher.dispatch(
        agent=args.agent,
        context=extra_context,
        output_files=args.output or [],
        wait_for_approval=bool(args.wait_approval),
        gate_name=args.wait_approval,
        section_id=args.section,
        extra_system_prompt=args.extra_prompt,
    )

    # 결과 출력
    if result.success:
        print(f"✅ Dispatch successful | agent={result.agent} | run_id={result.run_id} | latency={result.latency_ms}ms")
        if result.output_files:
            print(f"   Output files: {result.output_files}")
    else:
        print(f"❌ Dispatch failed | agent={result.agent} | error={result.error}", file=sys.stderr)
        sys.exit(1)
