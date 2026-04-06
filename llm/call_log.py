"""LLM 호출 기록 저장 유틸리티."""
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Anthropic Claude pricing (PoC용, USD per 1M tokens)
CLAUDE_PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-20250514": {"input": 0.8, "output": 4.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
}

# OpenAI pricing (PoC용, USD per 1M tokens)
OPENAI_PRICING = {
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
}

# Provider detection
PROVIDER_MAP = {
    "claude-sonnet-4-20250514": "anthropic",
    "claude-haiku-4-20250514": "anthropic",
    "claude-opus-4-20250514": "anthropic",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gemini-1.5-pro": "google",
    "gemini-1.5-flash": "google",
}

CONTEXT_BUS_DIR = Path("context_bus")
RUNS_FILE = "runs.json"


@dataclass
class CallLogEntry:
    """LLM 호출 기록 단위."""
    run_id: str
    call_id: str
    agent: str
    model: str
    provider: str
    timestamp: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    status: str
    error: Optional[str]
    retry_count: int


def _utc_now() -> str:
    """ISO 8601 UTC 타임스탬프 반환."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_pricing(model: str) -> Optional[dict]:
    """모델 이름으로 토큰 단가를 조회."""
    if model in CLAUDE_PRICING:
        return CLAUDE_PRICING[model]
    if model in OPENAI_PRICING:
        return OPENAI_PRICING[model]
    return None


def get_current_run_id() -> str:
    """log_event.py의 runs.json에서 현재 활성 run_id를 읽어 반환.

    Returns:
        str: 활성 run_id. 없으면 'RUN-UNDETERMINED'.
    """
    runs_path = CONTEXT_BUS_DIR / RUNS_FILE
    if not runs_path.exists():
        return "RUN-UNDETERMINED"
    try:
        with open(runs_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            runs = json.loads(content) if content else []
    except (json.JSONDecodeError, IOError):
        return "RUN-UNDETERMINED"

    for run in reversed(runs):
        if run.get("ended_at") is None:
            return run.get("run_id", "RUN-UNDETERMINED")
    return "RUN-UNDETERMINED"


def generate_call_id() -> str:
    """고유 call_id 생성. 형식: CALL-{timestamp}-{seq}"""
    ts = int(time.time() * 1000)
    seq = ts % 1000
    return f"CALL-{ts}-{seq:03d}"


def calculate_cost(model: str, usage: dict) -> float:
    """토큰 사용량 기반 USD 비용 추정.

    Args:
        model: 모델명
        usage: {"prompt_tokens": int, "completion_tokens": int}

    Returns:
        float: USD 비용 (소수점 6자리)
    """
    pricing = _get_pricing(model)
    if pricing is None:
        return 0.0

    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    cost = (
        (prompt_tokens / 1_000_000) * pricing["input"]
        + (completion_tokens / 1_000_000) * pricing["output"]
    )
    return round(cost, 6)


def save_call_log(entry: CallLogEntry, log_path: str = "llm/call_log.jsonl") -> None:
    """CallLogEntry를 JSONL 파일에 append.

    Args:
        entry: 저장할 로그 엔트리
        log_path: 대상 JSONL 파일 경로 (기본: llm/call_log.jsonl)
    """
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(asdict(entry), ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + chr(10))


def load_call_log(log_path: str = "llm/call_log.jsonl") -> list[CallLogEntry]:
    """JSONL 파일에서 모든 CallLogEntry를 읽어 반환.

    Args:
        log_path: 대상 JSONL 파일 경로

    Returns:
        list[CallLogEntry]: 로그 엔트리 목록 (빈 리스트 if 파일 없음)
    """
    path = Path(log_path)
    if not path.exists():
        return []

    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(CallLogEntry(**data))
                except (json.JSONDecodeError, TypeError):
                    continue
    except IOError:
        pass

    return entries


def get_recent_calls(agent: Optional[str] = None, limit: int = 10) -> list[CallLogEntry]:
    """JSONL에서 가장 최근 호출을 역순으로 조회.

    Args:
        agent: 에이전트명 필터 (None이면 전체)
        limit: 반환 최대 개수

    Returns:
        list[CallLogEntry]: 최신부터 정렬된 엔트리 목록
    """
    path = Path("llm/call_log.jsonl")
    if not path.exists():
        return []

    recent: list[CallLogEntry] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except IOError:
        return []

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            entry = CallLogEntry(**data)
            if agent is None or entry.agent == agent:
                recent.append(entry)
                if len(recent) >= limit:
                    break
        except (json.JSONDecodeError, TypeError):
            continue

    return recent


def get_stats(agent: Optional[str] = None) -> dict:
    """호출 통계를 반환.

    Args:
        agent: 에이전트명 필터 (None이면 전체)

    Returns:
        dict: {
            "total_calls": int,
            "success_count": int,
            "error_count": int,
            "avg_latency_ms": float,
            "total_cost_usd": float,
            "success_rate": float,
            "total_tokens": int,
        }
    """
    entries = load_call_log()
    if agent is not None:
        entries = [e for e in entries if e.agent == agent]

    if not entries:
        return {
            "total_calls": 0,
            "success_count": 0,
            "error_count": 0,
            "avg_latency_ms": 0.0,
            "total_cost_usd": 0.0,
            "success_rate": 0.0,
            "total_tokens": 0,
        }

    total = len(entries)
    success = sum(1 for e in entries if e.status == "success")
    errors = sum(1 for e in entries if e.status in ("error", "retry_exhausted"))
    total_cost = sum(e.cost_usd for e in entries)
    total_latency = sum(e.latency_ms for e in entries)
    total_tokens = sum(e.total_tokens for e in entries)

    return {
        "total_calls": total,
        "success_count": success,
        "error_count": errors,
        "avg_latency_ms": round(total_latency / total, 3),
        "total_cost_usd": round(total_cost, 6),
        "success_rate": round(success / total, 4),
        "total_tokens": total_tokens,
    }
