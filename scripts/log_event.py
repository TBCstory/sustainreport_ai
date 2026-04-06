#!/usr/bin/env python3.13
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from scripts.utils import generate_run_id

LOG_DIR = "context_bus"
EVENTS_FILE = "events.jsonl"
RUNS_FILE = "runs.json"
INCIDENTS_FILE = "incidents.json"

EVENT_TYPES = ["progress", "gate_passed", "gate_blocked", "incident", "milestone", "override"]
AGENTS = [
    "toc-planner",
    "framework-mapper",
    "section-writer",
    "internal-reviewer",
    "fact-checker",
    "provenance-builder",
    "data-analyst",
]
PHASES = ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7"]
SEVERITIES = ["low", "medium", "high", "blocker"]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_workspace_path(workspace: Optional[str]) -> Path:
    return Path(workspace) if workspace else Path.cwd()


def ensure_context_bus(workspace_path: Path) -> Path:
    bus_dir = workspace_path / LOG_DIR
    bus_dir.mkdir(parents=True, exist_ok=True)
    return bus_dir


def load_json_array(file_path: Path) -> list:
    if not file_path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return json.loads(content) if content else []
    except (json.JSONDecodeError, IOError):
        return []


def save_json_array(file_path: Path, data: list) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_next_incident_id(incidents: list) -> str:
    if not incidents:
        return "INC-001"
    max_id = 0
    for inc in incidents:
        try:
            num = int(inc.get("incident_id", "INC-000").replace("INC-", ""), 10)
            if num > max_id:
                max_id = num
        except ValueError:
            continue
    return "INC-" + str(max_id + 1).zfill(3)


def parse_details(details_str: Optional[str]) -> dict:
    if not details_str:
        return {}
    try:
        return json.loads(details_str)
    except json.JSONDecodeError:
        click.echo("Warning: Invalid JSON in --details: " + details_str, err=True)
        return {"raw": details_str}


def log_to_jsonl(event: dict, bus_dir: Path) -> None:
    with open(bus_dir / EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + chr(10))


def log_progress(agent, phase, section, message, run_id, bus_dir):
    log_to_jsonl(
        {
            "timestamp": utc_now(),
            "type": "progress",
            "agent": agent,
            "phase": phase,
            "section": section,
            "message": message,
            "run_id": run_id,
        },
        bus_dir,
    )


def log_gate_passed(gate, agent, phase, section, message, run_id, bus_dir):
    log_to_jsonl(
        {
            "timestamp": utc_now(),
            "type": "gate_passed",
            "gate": gate,
            "agent": agent,
            "phase": phase,
            "section": section,
            "message": message,
            "run_id": run_id,
        },
        bus_dir,
    )


def log_gate_blocked(gate, reason, agent, phase, section, message, run_id, bus_dir):
    log_to_jsonl(
        {
            "timestamp": utc_now(),
            "type": "gate_blocked",
            "gate": gate,
            "reason": reason,
            "agent": agent,
            "phase": phase,
            "section": section,
            "message": message,
            "run_id": run_id,
        },
        bus_dir,
    )
    incidents = load_json_array(bus_dir / INCIDENTS_FILE)
    incidents.append(
        {
            "incident_id": get_next_incident_id(incidents),
            "timestamp": utc_now(),
            "severity": "blocker",
            "type": "gate_blocked",
            "gate": gate,
            "reason": reason,
            "resolved": False,
            "details": {},
        }
    )
    save_json_array(bus_dir / INCIDENTS_FILE, incidents)


def log_incident(severity, message, details, agent, phase, section, run_id, bus_dir):
    log_to_jsonl(
        {
            "timestamp": utc_now(),
            "type": "incident",
            "severity": severity,
            "agent": agent,
            "phase": phase,
            "section": section,
            "message": message,
            "run_id": run_id,
        },
        bus_dir,
    )
    incidents = load_json_array(bus_dir / INCIDENTS_FILE)
    incidents.append(
        {
            "incident_id": get_next_incident_id(incidents),
            "timestamp": utc_now(),
            "severity": severity,
            "type": "incident",
            "gate": None,
            "reason": message,
            "resolved": False,
            "details": details,
        }
    )
    save_json_array(bus_dir / INCIDENTS_FILE, incidents)


def log_milestone(message, phase, section, run_id, bus_dir):
    log_to_jsonl(
        {
            "timestamp": utc_now(),
            "type": "milestone",
            "phase": phase,
            "section": section,
            "message": message,
            "run_id": run_id,
        },
        bus_dir,
    )


def log_override(message, agent, phase, section, details, bus_dir):
    log_to_jsonl(
        {
            "timestamp": utc_now(),
            "type": "override",
            "agent": agent,
            "phase": phase,
            "section": section,
            "message": message,
            "details": details,
        },
        bus_dir,
    )


def get_active_run(bus_dir):
    runs = load_json_array(bus_dir / RUNS_FILE)
    for run in reversed(runs):
        if run.get("ended_at") is None:
            return run
    return None


def ensure_run(agent, phase, section, bus_dir):
    active = get_active_run(bus_dir)
    if active:
        if agent and agent not in active.get("agents", []):
            active["agents"].append(agent)
        if phase and phase not in active.get("phases", []):
            active["phases"].append(phase)
        if section and section not in active.get("sections", []):
            active["sections"].append(section)
        active["events_count"] = active.get("events_count", 0) + 1
        return active["run_id"]
    run_id = generate_run_id()
    runs = load_json_array(bus_dir / RUNS_FILE)
    runs.append(
        {
            "run_id": run_id,
            "started_at": utc_now(),
            "ended_at": None,
            "agents": [agent] if agent else [],
            "phases": [phase] if phase else [],
            "sections": [section] if section else [],
            "events_count": 1,
            "outcome": None,
        }
    )
    save_json_array(bus_dir / RUNS_FILE, runs)
    return run_id


def close_run(run_id, outcome, bus_dir):
    runs = load_json_array(bus_dir / RUNS_FILE)
    for run in runs:
        if run.get("run_id") == run_id:
            run["ended_at"] = utc_now()
            run["outcome"] = outcome
            break
    save_json_array(bus_dir / RUNS_FILE, runs)


def log_event(
    event_type: str,
    message: str,
    agent: Optional[str] = None,
    phase: Optional[str] = None,
    section: Optional[str] = None,
    gate: Optional[str] = None,
    reason: Optional[str] = None,
    severity: Optional[str] = None,
    details: Optional[dict] = None,
    run_id: Optional[str] = None,
    workspace: Optional[str] = None,
) -> None:
    """
    범용 이벤트 로깅 함수. event_type에 따라 적절한 로그 함수를 호출한다.

    Args:
        event_type: "progress" | "gate_passed" | "gate_blocked" | "incident" | "milestone" | "override"
        message: 로그 메시지
        agent: 에이전트 이름
        phase: Phase (P0-P7)
        section: 섹션 ID
        gate: 게이트 ID
        reason: 차단 이유
        severity: incident severity
        details: 추가 상세 정보
        run_id: 실행 ID
        workspace: 워크스페이스 경로
    """
    workspace_path = get_workspace_path(workspace)
    bus_dir = ensure_context_bus(workspace_path)
    run_id = run_id or ensure_run(agent, phase, section, bus_dir)

    if event_type == "progress":
        log_progress(agent, phase, section, message, run_id, bus_dir)
    elif event_type == "gate_passed":
        log_gate_passed(gate, agent, phase, section, message, run_id, bus_dir)
    elif event_type == "gate_blocked":
        log_gate_blocked(gate, reason, agent, phase, section, message, run_id, bus_dir)
    elif event_type == "incident":
        log_incident(severity, message, details, agent, phase, section, run_id, bus_dir)
    elif event_type == "milestone":
        log_milestone(message, phase, section, run_id, bus_dir)
    elif event_type == "override":
        log_override(message, agent, phase, section, details, bus_dir)
    else:
        log_to_jsonl(
            {
                "timestamp": utc_now(),
                "type": event_type,
                "agent": agent,
                "phase": phase,
                "section": section,
                "message": message,
                "run_id": run_id,
            },
            bus_dir,
        )


@click.command()
@click.option("--type", "event_type", type=click.Choice(EVENT_TYPES), required=True, help="Event type")
@click.option("--agent", type=click.Choice(AGENTS), default=None, help="Agent name")
@click.option("--phase", type=click.Choice(PHASES), default=None, help="Current phase (P0-P7)")
@click.option("--section", default=None, help="Section ID (SEC-X.Y.Z)")
@click.option("--message", required=True, help="Event message")
@click.option("--gate", default=None, help="Gate ID (e.g., P2_to_P3)")
@click.option("--reason", default=None, help="Blocking reason")
@click.option("--severity", type=click.Choice(SEVERITIES), default=None, help="Incident severity")
@click.option("--details", default=None, help="Additional details (JSON string)")
@click.option("--workspace", default=None, help="Workspace path (default: current directory)")
@click.option("--close-run", "close_run_flag", is_flag=True, default=False, help="Close current run")
@click.option(
    "--run-outcome", type=click.Choice(["success", "failed", "cancelled"]), default="success", help="Run outcome"
)
def main(
    event_type, agent, phase, section, message, gate, reason, severity, details, workspace, close_run_flag, run_outcome
):
    try:
        bus_dir = ensure_context_bus(get_workspace_path(workspace))
        details_dict = parse_details(details)
        if close_run_flag:
            active = get_active_run(bus_dir)
            if active:
                close_run(active["run_id"], run_outcome, bus_dir)
                click.echo("Run " + active["run_id"] + " closed with outcome: " + run_outcome)
            else:
                click.echo("No active run to close", err=True)
                sys.exit(1)
            return
        run_id = ensure_run(agent, phase, section, bus_dir)
        if event_type == "progress":
            log_progress(agent, phase, section, message, run_id, bus_dir)
        elif event_type == "gate_passed":
            if not gate:
                click.echo("Error: --gate required for gate_passed event", err=True)
                sys.exit(1)
            log_gate_passed(gate, agent, phase, section, message, run_id, bus_dir)
        elif event_type == "gate_blocked":
            if not gate or not reason:
                click.echo("Error: --gate and --reason required for gate_blocked event", err=True)
                sys.exit(1)
            log_gate_blocked(gate, reason, agent, phase, section, message, run_id, bus_dir)
        elif event_type == "incident":
            if not severity:
                click.echo("Error: --severity required for incident event", err=True)
                sys.exit(1)
            log_incident(severity, message, details_dict, agent, phase, section, run_id, bus_dir)
        elif event_type == "milestone":
            log_milestone(message, phase, section, run_id, bus_dir)
        elif event_type == "override":
            log_override(message, agent, phase, section, details_dict, bus_dir)
        click.echo("Event logged: " + event_type + " | run_id: " + run_id)
    except Exception as e:
        click.echo("Error: " + str(e), err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
