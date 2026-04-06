#!/usr/bin/env python3.13
"""
요약 재구축 스크립트 — blocking_issues.json과 next_actions.json 갱신

사용법:
  python scripts/rebuild_summaries.py --workspace /path/to/PRJ-YYYY-CODE-NNN
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_json(path: Path) -> dict[str, Any] | None:
    """Load JSON file if exists, otherwise return None."""
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL file line by line."""
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_id(existing: list[dict[str, Any]], prefix: str, used_ids: set[str] | None = None) -> str:
    """Generate next ID like BLK-NNN or ACT-NNN.

    Tracks IDs generated in the current run via used_ids set to avoid
    assigning the same ID multiple times within one execution.
    """
    max_num = 0
    # Check existing items
    for item in existing:
        issue_id = item.get("issue_id", item.get("action_id", ""))
        if issue_id.startswith(prefix):
            try:
                num = int(issue_id[len(prefix) :])
                if num > max_num:
                    max_num = num
            except ValueError:
                continue
    # Check IDs already generated in this run
    if used_ids is not None:
        for rid in used_ids:
            if rid.startswith(prefix):
                try:
                    num = int(rid[len(prefix) :])
                    if num > max_num:
                        max_num = num
                except ValueError:
                    continue
    new_id = f"{prefix}{max_num + 1:03d}"
    if used_ids is not None:
        used_ids.add(new_id)
    return new_id


def severity_rank(severity: str) -> int:
    """Higher rank = more severe."""
    return {"blocker": 4, "high": 3, "medium": 2, "low": 1}.get(severity, 0)


def _is_issue_resolved(issue: dict[str, Any]) -> bool:
    """Check if an issue is resolved.

    Handles two canonical shapes:
    - BLK- style: {"status": "resolved"}
    - BK- style:  {"resolved": True}
    """
    if issue.get("status") == "resolved":
        return True
    if issue.get("resolved") is True:
        return True
    return False


def action_identity_key(action: dict[str, Any]) -> str:
    """Build a stable identity key for next actions."""
    query_id = action.get("query_id", "")
    if query_id:
        return f"query:{query_id}"

    issue_id = action.get("issue_id", "")
    if issue_id:
        return f"issue:{issue_id}"

    return f"{action.get('section_id', '')}:{action.get('type', '')}:{action.get('description', '')[:60]}"


def reserve_action_id(
    actions: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    existing_act: dict[str, Any] | None,
    used_ids: set[str] | None,
) -> str:
    """Reuse an existing action_id once, otherwise assign a fresh canonical one."""
    candidate = existing_act.get("action_id", "") if existing_act else ""

    if candidate:
        if used_ids is not None:
            if candidate not in used_ids:
                used_ids.add(candidate)
                return candidate
        else:
            if candidate not in {action.get("action_id", "") for action in actions}:
                return candidate

    return next_id(actions + existing, "ACT-", used_ids)


# ---------------------------------------------------------------------------
# Source readers
# ---------------------------------------------------------------------------


def read_phase_rules(workspace: Path) -> dict[str, Any] | None:
    """Read phase_rules.json from orchestration directory."""
    path = Path(__file__).parent.parent / "orchestration" / "phase_rules.json"
    return load_json(path)


def read_project_state(workspace: Path) -> dict[str, Any] | None:
    """Read project_state.json."""
    return load_json(workspace / "project_state.json")


def read_incidents(workspace: Path) -> list[dict[str, Any]]:
    """Read context_bus/incidents.json (JSON Array format)."""
    data = load_json(workspace / "context_bus" / "incidents.json")
    return data if isinstance(data, list) else []


def read_events(workspace: Path) -> list[dict[str, Any]]:
    """Read context_bus/events.jsonl."""
    return load_jsonl(workspace / "context_bus" / "events.jsonl")


def read_runs(workspace: Path) -> list[dict[str, Any]]:
    """Read context_bus/runs.json."""
    data = load_json(workspace / "context_bus" / "runs.json")
    return data if isinstance(data, list) else []


def read_draft_meta_files(workspace: Path) -> list[dict[str, Any]]:
    """Read all 07_drafts/*_meta.json files."""
    drafts_dir = workspace / "07_drafts"
    if not drafts_dir.exists():
        return []
    meta_files = sorted(drafts_dir.glob("*_meta.json"))
    results = []
    for fp in meta_files:
        data = load_json(fp)
        if data:
            results.append(data)
    return results


def read_internal_review_report(workspace: Path) -> dict[str, Any] | None:
    """Read 08_review/internal_review_report.json."""
    return load_json(workspace / "08_review" / "internal_review_report.json")


def read_fact_check_report(workspace: Path) -> dict[str, Any] | None:
    """Read 08_review/fact_check_report.json."""
    return load_json(workspace / "08_review" / "fact_check_report.json")


def read_draft_queries(workspace: Path) -> list[dict[str, Any]]:
    """Read draft_queries.json."""
    data = load_json(workspace / "draft_queries.json")
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "queries" in data:
        return data["queries"]
    return []


def read_existing_blocking_issues(workspace: Path) -> dict[str, Any] | None:
    """Read existing blocking_issues.json if exists."""
    return load_json(workspace / "blocking_issues.json")


def read_existing_next_actions(workspace: Path) -> dict[str, Any] | None:
    """Read existing next_actions.json if exists."""
    return load_json(workspace / "next_actions.json")


# ---------------------------------------------------------------------------
# Issue extraction
# ---------------------------------------------------------------------------


def extract_from_incidents(
    incidents: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    used_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Extract blocking issues from incidents with severity blocker|high."""
    blockers = []
    for inc in incidents:
        severity = inc.get("severity", "").lower()
        if severity not in ("blocker", "high"):
            continue

        # Find existing issue with same incident_id to preserve ID
        incident_id = inc.get("incident_id", "")
        matched_existing = None
        for ex in existing:
            if ex.get("incident_id") == incident_id:
                matched_existing = ex
                break

        issue: dict[str, Any] = {
            "issue_id": matched_existing["issue_id"] if matched_existing else next_id(blockers, "BLK-", used_ids),
            "severity": severity,
            "category": inc.get("category", "incident"),
            "section_id": inc.get("section_id", ""),
            "description": inc.get("description", inc.get("message", "")),
            "related_segments": inc.get("related_segments", []),
            "query_id": inc.get("query_id", ""),
            "incident_id": incident_id,
            "status": matched_existing["status"] if matched_existing else "open",
            "created_at": matched_existing["created_at"] if matched_existing else inc.get("timestamp", now_iso()),
            "updated_at": now_iso(),
        }
        blockers.append(issue)
    return blockers


def extract_from_draft_meta(
    draft_metas: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    used_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Extract missing_evidence and source_conflicts from draft meta files."""
    issues = []

    for meta in draft_metas:
        section_id = meta.get("section_id", "")
        section_issues = []

        # missing_evidence
        for ev in meta.get("missing_evidence", []):
            sev = ev.get("severity", "medium")
            if severity_rank(sev) < severity_rank("medium"):
                continue
            section_issues.append(
                {
                    "issue_id": next_id(issues + existing, "BLK-", used_ids),
                    "severity": sev,
                    "category": "missing_evidence",
                    "section_id": section_id,
                    "description": ev.get("description", ""),
                    "related_segments": ev.get("related_segments", []),
                    "query_id": ev.get("query_id", ""),
                    "status": "open",
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                    "source": "draft_meta",
                }
            )

        # source_conflicts
        for sc in meta.get("source_conflicts", []):
            if sc.get("resolution", "pending") == "pending":
                section_issues.append(
                    {
                        "issue_id": next_id(issues + existing, "BLK-", used_ids),
                        "severity": "high",
                        "category": "unresolved_conflict",
                        "section_id": section_id,
                        "description": sc.get("description", ""),
                        "segment_ids": sc.get("segment_ids", []),
                        "status": "open",
                        "created_at": now_iso(),
                        "updated_at": now_iso(),
                        "source": "draft_meta",
                    }
                )

        issues.extend(section_issues)

    return issues


def extract_from_fact_check_report(
    report: dict[str, Any] | None,
    existing: list[dict[str, Any]],
    used_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Extract critical_fact_errors from fact check report."""
    if not report:
        return []
    issues = []
    for err in report.get("mismatches", []):
        severity = err.get("severity", "medium")
        if severity_rank(severity) < severity_rank("high"):
            continue
        issues.append(
            {
                "issue_id": next_id(issues + existing, "BLK-", used_ids),
                "severity": severity,
                "category": "fact_error",
                "section_id": err.get("section_id", ""),
                "description": err.get("description", err.get("message", "")),
                "related_segments": err.get("related_segments", []),
                "status": "open",
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "source": "fact_check_report",
            }
        )
    return issues


def extract_from_review_report(
    report: dict[str, Any] | None,
    existing: list[dict[str, Any]],
    used_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Extract blocking_issues array from internal review report."""
    if not report:
        return []
    issues = []
    for bi in report.get("issues", []):
        existing_match = None
        for ex in existing:
            if ex.get("review_issue_id") == bi.get("issue_id"):
                existing_match = ex
                break
        issues.append(
            {
                "issue_id": existing_match["issue_id"]
                if existing_match
                else next_id(issues + existing, "BLK-", used_ids),
                "severity": bi.get("severity", "high"),
                "category": bi.get("category", "review_finding"),
                "section_id": bi.get("section_id", ""),
                "description": bi.get("description", ""),
                "related_segments": bi.get("related_segments", []),
                "query_id": bi.get("query_id", ""),
                "review_issue_id": bi.get("issue_id", ""),
                "status": existing_match["status"] if existing_match else "open",
                "created_at": existing_match["created_at"] if existing_match else now_iso(),
                "updated_at": now_iso(),
                "source": "internal_review_report",
            }
        )
    return issues


def merge_blocking_issues(
    sources: list[list[dict[str, Any]]],
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge all issue sources, deduplicating by normalized description."""
    seen_descriptions: dict[str, dict[str, Any]] = {}
    resolved_keep: list[dict[str, Any]] = []
    open_keep: list[dict[str, Any]] = []

    # Keep existing resolved issues (they don't get regenerated)
    # Use _is_issue_resolved to handle both status="resolved" and resolved=True
    for ex in existing:
        if _is_issue_resolved(ex):
            resolved_keep.append(ex)
        else:
            # Preserve existing open issues (they carry identity even when sources are empty)
            open_keep.append(ex)
        key = f"{ex.get('section_id', '')}:{ex.get('description', '')[:80]}"
        seen_descriptions[key] = ex

    # Process all new/open issues
    # Use _is_issue_resolved to handle both status="resolved" and resolved=True
    all_new: list[dict[str, Any]] = []
    for source_list in sources:
        for item in source_list:
            if _is_issue_resolved(item):
                continue
            key = f"{item.get('section_id', '')}:{item.get('description', '')[:80]}"
            if key not in seen_descriptions:
                seen_descriptions[key] = item
                all_new.append(item)
            else:
                # Merge segments and related_segments
                existing_item = seen_descriptions[key]
                for seg in item.get("related_segments", []):
                    if seg not in existing_item.get("related_segments", []):
                        existing_item["related_segments"] = existing_item.get("related_segments", []) + [seg]
                # Take highest severity
                if severity_rank(item.get("severity", "")) > severity_rank(existing_item.get("severity", "")):
                    existing_item["severity"] = item["severity"]

    # Sort: blocker first, then high, then by section_id
    all_issues = resolved_keep + open_keep + all_new
    all_issues.sort(key=lambda x: (-severity_rank(x.get("severity", "low")), x.get("section_id", "")))
    return all_issues


# ---------------------------------------------------------------------------
# Next actions generation
# ---------------------------------------------------------------------------


def generate_next_actions(
    draft_queries: list[dict[str, Any]],
    blocking_issues: list[dict[str, Any]],
    phase_rules: dict[str, Any] | None,
    project_state: dict[str, Any] | None,
    existing: list[dict[str, Any]],
    used_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Generate next actions from draft queries, blocking issues, and phase rules."""
    actions: list[dict[str, Any]] = []
    existing_by_identity: dict[str, dict[str, Any]] = {}

    for ex in existing:
        if ex.get("status") != "completed":
            existing_by_identity[action_identity_key(ex)] = ex

    # From open draft queries
    for dq in draft_queries:
        if dq.get("status") != "open":
            continue
        section_id = dq.get("section_id", "")
        lookup_key = action_identity_key(
            {
                "type": "data_request",
                "section_id": section_id,
                "description": dq.get("question", dq.get("description", "")),
                "query_id": dq.get("query_id", ""),
            }
        )
        existing_act = existing_by_identity.get(lookup_key)

        priority_map = {"critical": 1, "high": 2, "medium": 3, "low": 4}
        priority = priority_map.get(dq.get("priority", "medium").lower(), 3)

        actions.append(
            {
                "action_id": reserve_action_id(actions, existing, existing_act, used_ids),
                "priority": existing_act["priority"] if existing_act else priority,
                "type": "data_request",
                "section_id": section_id,
                "description": dq.get("question", dq.get("description", "")),
                "query_id": dq.get("query_id", ""),
                "assignee": "consultant",
                "status": existing_act["status"] if existing_act else "pending",
                "deadline": dq.get("deadline", ""),
                "created_at": existing_act.get("created_at", dq.get("created_at", now_iso()))
                if existing_act
                else dq.get("created_at", now_iso()),
            }
        )

    # From open blocking issues
    for bi in blocking_issues:
        if bi.get("status") != "open":
            continue
        section_id = bi.get("section_id", "")
        category = bi.get("category", "")

        if category == "unresolved_conflict":
            action_type = "human_decision"
            description = f"해결 필요: {bi.get('description', '')}"
            assignee = "consultant_lead"
        elif category == "fact_error":
            action_type = "fact_correction"
            description = f"팩트 오류 수정: {bi.get('description', '')}"
            assignee = "consultant"
        elif category == "missing_evidence":
            action_type = "evidence_gathering"
            description = f"증거 확보: {bi.get('description', '')}"
            assignee = "consultant"
        else:
            action_type = "general_fix"
            description = f"차단 이슈 해결: {bi.get('description', '')}"
            assignee = "consultant"

        existing_act = existing_by_identity.get(
            action_identity_key(
                {
                    "type": action_type,
                    "section_id": section_id,
                    "description": description,
                    "issue_id": bi.get("issue_id", ""),
                }
            )
        )

        actions.append(
            {
                "action_id": reserve_action_id(actions, existing, existing_act, used_ids),
                "priority": existing_act["priority"] if existing_act else 2,
                "type": action_type,
                "section_id": section_id,
                "description": description,
                "issue_id": bi.get("issue_id", ""),
                "assignee": existing_act["assignee"] if existing_act else assignee,
                "status": existing_act["status"] if existing_act else "pending",
                "deadline": existing_act.get("deadline", "") if existing_act else "",
                "created_at": existing_act.get("created_at", now_iso()) if existing_act else now_iso(),
            }
        )

    # Phase-based suggestions
    current_phase = project_state.get("current_phase", "P0") if project_state else "P0"
    if phase_rules:
        phases = phase_rules.get("phases", {})
        phase_info = phases.get(current_phase, {})
        next_phase = phase_info.get("next_phase")
        if next_phase:
            phase_next_info = phases.get(next_phase, {})
            gate_req = phase_next_info.get("gate_required", False)
            if gate_req:
                actions.append(
                    {
                        "action_id": next_id(actions + existing, "ACT-", used_ids),
                        "priority": 5,
                        "type": "gate_approval",
                        "section_id": "",
                        "description": f"{current_phase}→{next_phase} 게이트 승인 필요",
                        "assignee": "project_manager",
                        "status": "pending",
                        "created_at": now_iso(),
                    }
                )

    # Deduplicate by section_id + type + description (first 60 chars)
    seen: dict[str, dict[str, Any]] = {}
    for act in actions:
        key = action_identity_key(act)
        if key not in seen or act.get("priority", 99) < seen[key].get("priority", 99):
            seen[key] = act

    result = list(seen.values())
    result.sort(key=lambda x: (x.get("priority", 99), x.get("section_id", "")))
    return result


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def compute_statistics(issues: list[dict[str, Any]]) -> dict[str, int]:
    """Compute statistics for blocking issues."""
    total = len(issues)
    open_count = sum(1 for i in issues if i.get("status") == "open")
    resolved = total - open_count
    blocker = sum(1 for i in issues if i.get("severity") == "blocker")
    return {
        "total": total,
        "open": open_count,
        "resolved": resolved,
        "blocker": blocker,
    }


# ---------------------------------------------------------------------------
# Main rebuild logic
# ---------------------------------------------------------------------------


def rebuild_blocking_issues(workspace: Path) -> dict[str, Any]:
    """Rebuild blocking_issues.json from all sources."""
    existing_data = read_existing_blocking_issues(workspace)
    existing_issues = existing_data.get("issues", []) if existing_data else []

    incidents = read_incidents(workspace)
    draft_metas = read_draft_meta_files(workspace)
    fact_report = read_fact_check_report(workspace)
    review_report = read_internal_review_report(workspace)

    # Track IDs generated in this run to avoid duplicates
    used_ids: set[str] = set()

    # Extract from each source (all use the same used_ids set)
    from_incidents = extract_from_incidents(incidents, existing_issues, used_ids)
    from_draft_meta = extract_from_draft_meta(draft_metas, existing_issues, used_ids)
    from_fact_check = extract_from_fact_check_report(fact_report, existing_issues, used_ids)
    from_review = extract_from_review_report(review_report, existing_issues, used_ids)

    # Merge all sources
    merged = merge_blocking_issues(
        [from_incidents, from_draft_meta, from_fact_check, from_review],
        existing_issues,
    )

    # Assign canonical IDs if any were missed (use same used_ids to avoid collisions)
    for i, issue in enumerate(merged):
        if not issue.get("issue_id", "").startswith("BLK-"):
            issue["issue_id"] = next_id(merged + existing_issues, "BLK-", used_ids)

    return {
        "generated_at": now_iso(),
        "issues": merged,
        "statistics": compute_statistics(merged),
    }


def rebuild_next_actions(workspace: Path, blocking_issues: list[dict[str, Any]]) -> dict[str, Any]:
    """Rebuild next_actions.json from all sources."""
    existing_data = read_existing_next_actions(workspace)
    existing_actions = existing_data.get("actions", []) if existing_data else []

    draft_queries = read_draft_queries(workspace)
    phase_rules = read_phase_rules(workspace)
    project_state = read_project_state(workspace)

    # Track IDs generated in this run to avoid duplicates
    used_ids: set[str] = set()

    actions = generate_next_actions(
        draft_queries,
        blocking_issues,
        phase_rules,
        project_state,
        existing_actions,
        used_ids,
    )

    # Assign canonical IDs if any were missed (use same used_ids to avoid collisions)
    for i, act in enumerate(actions):
        if not act.get("action_id", "").startswith("ACT-"):
            act["action_id"] = next_id(actions + existing_actions, "ACT-", used_ids)

    return {
        "generated_at": now_iso(),
        "actions": actions,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--workspace",
    "-w",
    "workspace_path",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="경로 to project workspace (e.g. /path/to/PRJ-YYYY-CODE-NNN)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print output without writing files",
)
def main(workspace_path: Path, dry_run: bool) -> int:
    """Rebuild blocking_issues.json and next_actions.json from source files."""
    workspace = workspace_path.resolve()

    # Validate workspace structure
    if not (workspace / "07_drafts").exists():
        click.echo("Error: 07_drafts directory not found. Is this a valid workspace?", err=True)
        return 1

    context_bus = workspace / "context_bus"
    if not context_bus.exists():
        click.echo("Warning: context_bus directory not found. Some data may be missing.", err=True)

    try:
        # Rebuild blocking_issues
        blocking_data = rebuild_blocking_issues(workspace)

        # Rebuild next_actions (depends on blocking_issues)
        next_actions_data = rebuild_next_actions(workspace, blocking_data.get("issues", []))

        if dry_run:
            click.echo("=== blocking_issues.json ===")
            click.echo(json.dumps(blocking_data, indent=2, ensure_ascii=False))
            click.echo("\n=== next_actions.json ===")
            click.echo(json.dumps(next_actions_data, indent=2, ensure_ascii=False))
            return 0

        # Write blocking_issues.json
        bi_path = workspace / "blocking_issues.json"
        with open(bi_path, "w", encoding="utf-8") as f:
            json.dump(blocking_data, f, indent=2, ensure_ascii=False)
        click.echo(f"Written: {bi_path}")

        # Write next_actions.json
        na_path = workspace / "next_actions.json"
        with open(na_path, "w", encoding="utf-8") as f:
            json.dump(next_actions_data, f, indent=2, ensure_ascii=False)
        click.echo(f"Written: {na_path}")

        # Summary
        bi_stats = blocking_data.get("statistics", {})
        click.echo(
            f"\nSummary: {bi_stats.get('total', 0)} issues "
            f"({bi_stats.get('open', 0)} open, {bi_stats.get('resolved', 0)} resolved, "
            f"{bi_stats.get('blocker', 0)} blockers)"
        )
        click.echo(f"Actions: {len(next_actions_data.get('actions', []))} next actions generated")

        return 0

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
