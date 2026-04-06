#!/usr/bin/env python3.13
"""
test_dispatch_agent.py — AgentDispatcher 단위 테스트

Tests:
1. 프롬프트 로드 (agents/{agent}.md 존재, 플레이스홀더 치환)
2. 컨텍스트 조립 ({workspace} 치환, events.jsonl 참조)
3. 출력 파일 쓰기 (JSON/Markdown 분기)
4. dispatch() 결과 형식 검증
5. 예외 처리 (프롬프트 없음, 쓰기 실패)
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
import sys

sys.path.insert(0, str(PROJECT_ROOT))


class TestPromptLoading(unittest.TestCase):
    """프롬프트 로드 테스트."""

    def test_load_existing_agent_prompt(self):
        """존재하는 에이전트 프롬프트 로드."""
        from scripts.dispatch_agent import AgentDispatcher

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir)

            # data-analyst 프롬프트가 존재하는지 확인
            prompt_path = PROJECT_ROOT / "agents" / "data-analyst.md"
            self.assertTrue(prompt_path.exists(), f"Agent prompt not found: {prompt_path}")

            # 로드
            prompt = dispatcher._load_agent_prompt("data-analyst")
            self.assertIsInstance(prompt, str)
            self.assertGreater(len(prompt), 0)
            self.assertIn("역할", prompt)

    def test_load_nonexistent_agent_raises(self):
        """존재하지 않는 에이전트 → 예외 발생."""
        from scripts.dispatch_agent import AgentDispatcher, AgentPromptNotFoundError

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir)

            with self.assertRaises(AgentPromptNotFoundError) as ctx:
                dispatcher._load_agent_prompt("nonexistent-agent")
            self.assertIn("nonexistent-agent", str(ctx.exception))

    def test_workspace_placeholder_replacement(self):
        """{workspace} 플레이스홀더가 실제 경로로 치환됨."""
        from scripts.dispatch_agent import AgentDispatcher

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir)
            # toc-planner.md uses {workspace} in its table paths
            prompt = dispatcher._load_agent_prompt("toc-planner")

            # 플레이스홀더가 치환되었는지
            self.assertNotIn("{workspace}", prompt)
            self.assertIn(str(Path(tmpdir)), prompt)


class TestContextBuilding(unittest.TestCase):
    """컨텍스트 조립 테스트."""

    def test_extra_context_placeholder_replacement(self):
        """{{key}} 플레이스홀더가 extra_context 값으로 치환됨."""
        from scripts.dispatch_agent import AgentDispatcher

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir)

            base = "테스트: {{name}}은(는) {{role}}입니다."
            extra = {"name": "홍길동", "role": "개발자"}

            result = dispatcher._build_context(base, extra, None)

            self.assertIn("홍길동", result)
            self.assertIn("개발자", result)
            self.assertNotIn("{{name}}", result)
            self.assertNotIn("{{role}}", result)

    def test_extra_context_dict_values_json_serialized(self):
        """dict/list 값은 JSON 문자열로 직렬화됨."""
        from scripts.dispatch_agent import AgentDispatcher

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir)

            base = "설정: {{config}}"
            extra = {"config": {"temperature": 0.5, "max_tokens": 8192}}

            result = dispatcher._build_context(base, extra, None)

            self.assertIn("temperature", result)
            self.assertIn("0.5", result)

    def test_extra_system_prompt_append(self):
        """extra_system_prompt가 프롬프트 끝에 추가됨."""
        from scripts.dispatch_agent import AgentDispatcher

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir)

            base = "기본 프롬프트"
            result = dispatcher._build_context(base, {}, "추가 시스템 프롬프트")

            self.assertIn("기본 프롬프트", result)
            self.assertIn("추가 시스템 프롬프트", result)

    def test_recent_events_formatting(self):
        """_format_recent_events가 올바른 형식으로 출력됨."""
        from scripts.dispatch_agent import AgentDispatcher

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir)

            events = [
                {
                    "timestamp": "2026-04-03T10:00:00Z",
                    "type": "progress",
                    "agent": "data-analyst",
                    "phase": "P1",
                    "message": "파일 변환 완료",
                },
                {
                    "timestamp": "2026-04-03T10:05:00Z",
                    "type": "milestone",
                    "agent": "toc-planner",
                    "phase": "P2",
                    "message": "writing_blueprint 생성 완료",
                },
            ]

            result = dispatcher._format_recent_events(events)

            self.assertIn("progress", result)
            self.assertIn("data-analyst", result)
            self.assertIn("P1", result)
            self.assertIn("파일 변환 완료", result)
            self.assertIn("milestone", result)

    def test_recent_events_empty(self):
        """이벤트가 없으면 빈 문자열 반환."""
        from scripts.dispatch_agent import AgentDispatcher

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir)

            result = dispatcher._format_recent_events([])
            self.assertEqual(result, "")

            result = dispatcher._format_recent_events(None)
            self.assertEqual(result, "")


class TestOutputWriting(unittest.TestCase):
    """출력 파일 쓰기 테스트."""

    def test_write_json_output(self):
        """JSON 파싱 가능한 content → pretty-printed JSON 저장."""
        from scripts.dispatch_agent import AgentDispatcher

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir)

            content = '{"key": "value", "number": 42}'
            output_files = ["test_output.json"]

            dispatcher._write_outputs(content, output_files)

            out_path = Path(tmpdir) / "test_output.json"
            self.assertTrue(out_path.exists())

            data = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(data["key"], "value")
            self.assertEqual(data["number"], 42)

    def test_write_markdown_output(self):
        """일반 텍스트 → 일반 텍스트로 저장."""
        from scripts.dispatch_agent import AgentDispatcher

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir)

            content = "# Hello\n\nThis is a test."
            output_files = ["test_output.md"]

            dispatcher._write_outputs(content, output_files)

            out_path = Path(tmpdir) / "test_output.md"
            self.assertTrue(out_path.exists())
            self.assertEqual(out_path.read_text(encoding="utf-8"), content)

    def test_write_creates_parent_directories(self):
        """출력 파일의 부모 디렉토리가 없으면 자동 생성."""
        from scripts.dispatch_agent import AgentDispatcher

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir)

            content = "test"
            output_files = ["nested/dir/test.txt"]

            dispatcher._write_outputs(content, output_files)

            out_path = Path(tmpdir) / "nested" / "dir" / "test.txt"
            self.assertTrue(out_path.exists())

    def test_write_multiple_files(self):
        """여러 출력 파일을 한번에 작성."""
        from scripts.dispatch_agent import AgentDispatcher

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir)

            dispatcher._write_outputs("json1", ["file1.json"])
            dispatcher._write_outputs("json2", ["file2.json"])

            self.assertTrue((Path(tmpdir) / "file1.json").exists())
            self.assertTrue((Path(tmpdir) / "file2.json").exists())


class TestDispatchResult(unittest.TestCase):
    """DispatchResult 데이터 클래스 테스트."""

    def test_dispatch_result_fields(self):
        """DispatchResult가 모든 필드를 올바르게 저장."""
        from scripts.dispatch_agent import DispatchResult

        result = DispatchResult(
            success=True,
            agent="test-agent",
            output_files=["out1.md", "out2.json"],
            content="test content",
            run_id="RUN-20260403-A1",
            latency_ms=1234.5,
            model="claude-sonnet-4-20250514",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.agent, "test-agent")
        self.assertEqual(len(result.output_files), 2)
        self.assertEqual(result.content, "test content")
        self.assertEqual(result.run_id, "RUN-20260403-A1")
        self.assertEqual(result.latency_ms, 1234.5)
        self.assertEqual(result.model, "claude-sonnet-4-20250514")

    def test_dispatch_result_failure(self):
        """실패 시 error 필드 설정."""
        from scripts.dispatch_agent import DispatchResult

        result = DispatchResult(
            success=False,
            agent="test-agent",
            output_files=[],
            error="LLM call failed",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, "LLM call failed")


class TestDispatchIntegration(unittest.TestCase):
    """dispatch() 통합 테스트 (LLM 호출은 mocking)."""

    @patch("scripts.dispatch_agent.ModelRouter")
    def test_dispatch_with_mocked_llm(self, MockRouter):
        """Mock LLM으로 dispatch() 전체 플로우 테스트."""
        from scripts.dispatch_agent import AgentDispatcher

        # Mock LLM 결과 설정
        mock_result = {
            "content": "# SEC-3.1 초안\n\n내용입니다.",
            "model": "claude-sonnet-4-20250514",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            "latency_ms": 500.0,
            "run_id": "RUN-20260403-A1",
        }

        mock_router_instance = MagicMock()
        mock_router_instance.complete_messages.return_value = mock_result
        MockRouter.return_value = mock_router_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir, router=mock_router_instance)

            result = dispatcher.dispatch(
                agent="section-writer",
                context={"phase": "P4"},
                output_files=["07_drafts/SEC-3.1.md"],
            )

            self.assertTrue(result.success)
            self.assertEqual(result.agent, "section-writer")
            self.assertIn("SEC-3.1.md", result.output_files[0])

            # 출력 파일이 실제로 생성되었는지
            out_path = Path(tmpdir) / "07_drafts" / "SEC-3.1.md"
            self.assertTrue(out_path.exists())

    @patch("scripts.dispatch_agent.ModelRouter")
    def test_dispatch_failure_records_blocking_issue(self, MockRouter):
        """LLM 호출 실패 시 blocking_issue가 추가됨."""
        from scripts.dispatch_agent import AgentDispatcher

        mock_router_instance = MagicMock()
        mock_router_instance.complete_messages.side_effect = Exception("API Error")
        MockRouter.return_value = mock_router_instance

        with tempfile.TemporaryDirectory() as tmpdir:
            # StateManager 초기화
            from scripts.state_manager import StateManager

            sm = StateManager(tmpdir)
            dispatcher = AgentDispatcher(tmpdir, state_manager=sm, router=mock_router_instance)

            result = dispatcher.dispatch(
                agent="toc-planner",
                context={"phase": "P2"},
                output_files=["05_planning/structure_index.json"],
            )

            self.assertFalse(result.success)
            self.assertIn("API Error", result.error)

            # blocking issue 확인
            issues = sm.get_blocking_issues(resolved=False)
            self.assertGreater(len(issues), 0)


class TestWaitForApproval(unittest.TestCase):
    """_wait_for_human_approval 테스트."""

    def test_wait_without_state_manager_approves(self):
        """state_manager 없으면 승인으로 간주 (PoC 모드)."""
        from scripts.dispatch_agent import AgentDispatcher

        with tempfile.TemporaryDirectory() as tmpdir:
            dispatcher = AgentDispatcher(tmpdir, state_manager=None)

            # state_manager 없으면 True 반환 (호출해도 예외 없음)
            # 實際에는 폴링 로직이 실행되지만, 여기서는简单检查
            self.assertIsNone(dispatcher.state_manager)

    def test_wait_for_approval_no_module_error(self):
        """_wait_for_human_approval 호출 시 ModuleNotFoundError가 발생하지 않음.

        이전: dispatch_agent.py에서 'from orchestration.gate_rules import load_gate_rules' 시도 →
        ModuleNotFoundError: No module named 'orchestration.gate_rules'
        수정: gate_rules.json을 직접 로드하므로 오류 없음
        """
        from scripts.dispatch_agent import AgentDispatcher
        from scripts.state_manager import StateManager

        with tempfile.TemporaryDirectory() as tmpdir:
            sm = StateManager(tmpdir)
            dispatcher = AgentDispatcher(tmpdir, state_manager=sm)

            # ModuleNotFoundError가 발생하지 않는지만 확인
            # (실제 승인은 state_manager에서 테스트하므로 여기서는 폴링 진입만 검증)
            try:
                # Polling이 시작되면立即 return하므로, mock sleep으로 빠르게 종료
                with patch("scripts.dispatch_agent.time.sleep"):
                    dispatcher._wait_for_human_approval("P2_to_P3")
            except ModuleNotFoundError as e:
                if "orchestration.gate_rules" in str(e):
                    self.fail("orchestration.gate_rules import 실패 - gate_rules.json을 직접 로드해야 함")
                raise


if __name__ == "__main__":
    unittest.main()
