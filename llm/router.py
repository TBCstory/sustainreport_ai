"""LLM 라우터 — litellm 기반 멀티모델 통합."""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import litellm
from litellm import APIError, RateLimitError

# ─────────────────────────────────────────────────────────────────────────────
# 내부 모듈 임포트
# ─────────────────────────────────────────────────────────────────────────────
from llm.call_log import CallLogEntry, calculate_cost, save_call_log
from scripts.utils import generate_run_id

CALL_LOG_PATH = "llm/call_log.jsonl"

# ─────────────────────────────────────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────────────────────────────────────


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────────────────────────
# ModelRouter
# ─────────────────────────────────────────────────────────────────────────────


class ModelRouter:
    """
    model_routing.json의 정책에 따라 에이전트별 모델 라우팅을 수행한다.

    PoC 모드: claude-sonnet-4-20250514 (primary) → claude-haiku-4-20250514 (fallback)
    운영 모드: agent_model_policy 기반 라우팅
    """

    def __init__(self, routing_config_path: str = "orchestration/model_routing.json"):
        self.routing_config_path = Path(routing_config_path)
        self._config = self._load_config()
        self._poc_mode = self._config.get("poc_mode", {})
        self._agent_policy = self._config.get("agent_model_policy", {})
        self._litellm_config = self._config.get("litellm_config", {})
        self._retry_policy = self._config.get("routing_rules", {}).get("retry_policy", {})

        # litellm 전역 설정
        litellm.drop_params = self._litellm_config.get("drop_params", True)
        litellm.set_verbose = self._litellm_config.get("set_verbose", False)

    # ─────────────────────────────────────────────────────────────────────────
    # 내부 메서드
    # ─────────────────────────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        if not self.routing_config_path.exists():
            raise FileNotFoundError(f"routing config not found: {self.routing_config_path}")
        with open(self.routing_config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _is_poc_mode(self) -> bool:
        return self._poc_mode.get("enabled", False)

    def _get_poc_primary(self) -> str:
        return self._poc_mode.get("default_model", "claude-sonnet-4-20250514")

    def _get_poc_fallback(self) -> str:
        return self._poc_mode.get("fallback_model", "claude-haiku-4-20250514")

    # ─────────────────────────────────────────────────────────────────────────
    # 공개 API
    # ─────────────────────────────────────────────────────────────────────────

    def get_model_for_agent(self, agent: str) -> str:
        """
        에이전트 이름에 해당하는 primary 모델명을 반환한다.

        PoC 모드: poc_mode.default_model 사용
        운영 모드: agent_model_policy.{agent}.primary_model 사용
        """
        if self._is_poc_mode():
            return self._get_poc_primary()

        agent_config = self._agent_policy.get(agent, {})
        if not agent_config:
            # Unknown agent → fallback to POC primary
            return self._get_poc_primary()
        return agent_config.get("primary_model", self._get_poc_primary())

    def get_model_config(self, agent: str) -> dict:
        """
        에이전트별 모델 설정(temperature, max_tokens 등)을 반환한다.

        PoC 모드: poc_mode 설정 우선
        운영 모드: agent_model_policy.{agent} 설정 사용
        """
        if self._is_poc_mode():
            return {
                "temperature": 0.5,
                "max_tokens": 16384,
                "request_timeout": self._litellm_config.get("request_timeout", 120),
            }

        agent_config = self._agent_policy.get(agent, {})
        if not agent_config:
            return {
                "temperature": 0.5,
                "max_tokens": 8192,
                "request_timeout": self._litellm_config.get("request_timeout", 120),
            }

        return {
            "temperature": agent_config.get("temperature", 0.5),
            "max_tokens": agent_config.get("max_tokens", 8192),
            "request_timeout": self._litellm_config.get("request_timeout", 120),
        }

    def _save_call_log(self, entry: dict, agent: str = "unknown") -> None:
        """모든 LLM 호출 후 call_log.save() 호출하여 실행 기록 저장."""
        call_entry = CallLogEntry(
            run_id=entry.get("run_id", "UNKNOWN"),
            call_id=f"CALL-{int(time.time() * 1000)}",
            agent=agent,
            model=entry.get("model", "unknown"),
            provider=entry.get("model", "unknown").split("-")[0] if "-" in entry.get("model", "") else "unknown",
            timestamp=utc_now(),
            latency_ms=entry.get("latency_ms", 0.0),
            prompt_tokens=entry.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=entry.get("usage", {}).get("completion_tokens", 0),
            total_tokens=entry.get("usage", {}).get("total_tokens", 0),
            cost_usd=calculate_cost(entry.get("model", ""), entry.get("usage", {})),
            status="success",
            error=None,
            retry_count=0,
        )
        save_call_log(call_entry, log_path=CALL_LOG_PATH)

    def complete(
        self,
        prompt: str,
        agent: str,
        **kwargs,
    ) -> dict:
        """
        단일 프롬프트로 LLM 호출을 수행한다.

        Returns:
            {"content": str, "model": str, "usage": dict, "latency_ms": float, "run_id": str}
        """
        messages = [{"role": "user", "content": prompt}]
        return self.complete_messages(messages, agent, **kwargs)

    def complete_messages(
        self,
        messages: list,
        agent: str,
        **kwargs,
    ) -> dict:
        """
        messages 형식으로 LLM 호출을 수행한다.

        retry_policy: rate_limit 또는 api_error 시 primary → fallback → abort
        PoC 모드: 항상 Claude 단일 모델 (fallback 포함)

        Returns:
            {"content": str, "model": str, "usage": dict, "latency_ms": float, "run_id": str}
        """
        run_id = generate_run_id()
        model = self.get_model_for_agent(agent)
        config = self.get_model_config(agent)
        request_timeout = config.pop("request_timeout", 120)

        max_retries = self._retry_policy.get("max_retries", 2)
        retry_on = self._retry_policy.get("retry_on", ["rate_limit", "api_error"])
        fallback_chain = self._retry_policy.get("fallback_chain", ["primary", "fallback", "abort"])

        # Determine fallback model
        if self._is_poc_mode():
            fallback_model = self._get_poc_fallback()
        else:
            agent_policy = self._agent_policy.get(agent, {})
            fallback_model = agent_policy.get("fallback", self._get_poc_fallback())

        chain = [model, fallback_model] if fallback_chain[0] == "primary" else [model]
        chain = [m for m in chain if m]  # deduplicate

        last_error: Optional[Exception] = None

        for attempt_idx, current_model in enumerate(chain):
            try:
                start_time = time.monotonic()

                response = litellm.completion(
                    model=current_model,
                    messages=messages,
                    temperature=config.get("temperature", 0.5),
                    max_tokens=config.get("max_tokens", 8192),
                    timeout=request_timeout,
                    **kwargs,
                )

                latency_ms = (time.monotonic() - start_time) * 1000

                result = {
                    "content": response.choices[0].message.content,
                    "model": current_model,
                    "usage": response.model_dump().get("usage", {}),
                    "latency_ms": round(latency_ms, 2),
                    "run_id": run_id,
                }

                # call_log 저장
                self._save_call_log(result, agent=agent)

                return result

            except (RateLimitError, APIError) as e:
                last_error = e
                should_retry = any(keyword in str(e).lower() for keyword in retry_on)
                if should_retry and attempt_idx < len(chain) - 1:
                    # fallback to next model in chain
                    continue
                else:
                    break

            except Exception as e:
                last_error = e
                break

        # All retries exhausted → abort
        raise LLMCallError(
            f"LLM call failed after {len(chain)} attempt(s): {last_error}",
            run_id=run_id,
            model=model,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # call_log 연동
    # ─────────────────────────────────────────────────────────────────────────

    def _save_call_log(self, entry: dict, agent: str = "unknown") -> None:
        """모든 LLM 호출 후 call_log.save() 호출하여 실행 기록 저장."""
        call_entry = CallLogEntry(
            run_id=entry.get("run_id", "UNKNOWN"),
            call_id=f"CALL-{int(time.time() * 1000)}",
            agent=agent,
            model=entry.get("model", "unknown"),
            provider=entry.get("model", "unknown").split("-")[0] if "-" in entry.get("model", "") else "unknown",
            timestamp=utc_now(),
            latency_ms=entry.get("latency_ms", 0.0),
            prompt_tokens=entry.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=entry.get("usage", {}).get("completion_tokens", 0),
            total_tokens=entry.get("usage", {}).get("total_tokens", 0),
            cost_usd=calculate_cost(entry.get("model", ""), entry.get("usage", {})),
            status="success",
            error=None,
            retry_count=0,
        )
        save_call_log(call_entry, log_path=CALL_LOG_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# 예외 클래스
# ─────────────────────────────────────────────────────────────────────────────


class LLMCallError(Exception):
    """LLM 호출 실패 시 발생."""

    def __init__(self, message: str, run_id: str, model: str):
        super().__init__(message)
        self.run_id = run_id
        self.model = model


# ─────────────────────────────────────────────────────────────────────────────
# CLI 진입점 (테스트용)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("=== ModelRouter Test ===")

    try:
        router = ModelRouter()

        # Agent 목록
        agents = [
            "data-analyst",
            "toc-planner",
            "section-writer",
            "internal-reviewer",
        ]

        for agent in agents:
            model = router.get_model_for_agent(agent)
            config = router.get_model_config(agent)
            poc = router._is_poc_mode()
            print(f"\n[{agent}]")
            print(f"  POC mode: {poc}")
            print(f"  Model: {model}")
            print(f"  Config: {config}")

        # 간단한 호출 테스트
        print("\n=== LLM Call Test ===")
        result = router.complete(
            prompt="What is the capital of France? Reply in one sentence.",
            agent="section-writer",
        )
        print(f"Model: {result['model']}")
        print(f"Latency: {result['latency_ms']}ms")
        print(f"Run ID: {result['run_id']}")
        print(f"Content: {result['content']}")
        print(f"Usage: {result['usage']}")

        print("\nAll tests passed.")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
