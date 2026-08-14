"""Audit whether the AI research loop is actually closed and continuously useful.

The audit is read-only.  It distinguishes healthy data/shadow collection from
the stronger claim that an AI idea can become a frozen, passported,
independently audited historical experiment without an unrecorded hand-off.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _parse_time(raw: Any) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _age_hours(raw: Any, now: datetime) -> float | None:
    value = _parse_time(raw)
    return max(0.0, (now - value).total_seconds() / 3600.0) if value else None


def _approved_lines(path: Path) -> list[str]:
    try:
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    except OSError:
        return []


def audit(root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ideas = _jsonl(root / "runtime/research/idea_intake_queue.jsonl")
    station = _json(root / "runtime/local_research_station/status.json", {})
    nightly = _json(root / "runtime/research_nightly/status.json", {})
    approved = _approved_lines(root / "configs/autoresearch/approved_specs.txt")
    proposals = []
    for path in sorted((root / "configs/research_proposals").glob("*.json")):
        proposal = _json(path, {})
        if proposal:
            proposals.append(proposal)

    idea_status: dict[str, int] = {}
    for idea in ideas:
        status = str(idea.get("status") or "missing")
        idea_status[status] = idea_status.get(status, 0) + 1
    explicit_links = sum(
        bool(idea.get("experiment_id") and idea.get("prereg_path") and idea.get("spec_path"))
        for idea in ideas
    )
    hash_pinned_approvals = sum(len(line.split()) >= 2 and len(line.split()[-1]) == 64 for line in approved)
    nightly_age = _age_hours(nightly.get("ts"), now)
    station_age = _age_hours(station.get("generated_at_utc"), now)
    station_jobs = list(station.get("jobs") or [])
    station_healthy = bool(station.get("healthy")) and bool(station_jobs) and all(
        item.get("state") == "healthy" and item.get("live_order_authority") is False
        for item in station_jobs
    )
    nightly_fresh = nightly_age is not None and nightly_age <= 24.0
    bridge_closed = bool(ideas) and explicit_links == len(ideas)
    approvals_hash_bound = bool(approved) and hash_pinned_approvals == len(approved)
    findings = []
    if station_healthy:
        findings.append("continuous_shadow_and_audit_collectors_healthy")
    else:
        findings.append("continuous_shadow_or_audit_collectors_not_confirmed")
    if not bridge_closed:
        findings.append("idea_to_prereg_spec_passport_result_bridge_open")
    if not nightly_fresh:
        findings.append("nightly_autoresearch_scheduler_status_stale")
    if not approvals_hash_bound:
        findings.append("approved_specs_are_name_bound_not_content_hash_bound")
    findings.append("ai_proposals_do_not_generate_or_modify_strategy_code")

    return {
        "schema_id": "research_pipeline_audit_v1",
        "generated_at_utc": now.isoformat(),
        "authority": "read_only_no_experiment_no_live_or_promotion_authority",
        "continuous_station": {
            "healthy": station_healthy,
            "status_age_hours": station_age,
            "jobs": len(station_jobs),
            "healthy_jobs": sum(item.get("state") == "healthy" for item in station_jobs),
            "live_order_authority": station.get("live_order_authority"),
        },
        "idea_intake": {
            "cards": len(ideas),
            "status_counts": idea_status,
            "cards_with_explicit_experiment_prereg_spec_links": explicit_links,
        },
        "historical_execution": {
            "nightly_status_age_hours": nightly_age,
            "nightly_status_fresh_le_24h": nightly_fresh,
            "approved_spec_entries": len(approved),
            "hash_pinned_approved_entries": hash_pinned_approvals,
            "pending_gate_proposals": sum(p.get("status") == "pending" for p in proposals),
        },
        "capabilities": {
            "ai_can_propose_complete_falsifiable_cards": True,
            "approved_existing_specs_can_be_executed_research_only": True,
            "idea_to_runnable_experiment_is_fully_automatic": bridge_closed,
            "approval_is_content_hash_bound": approvals_hash_bound,
            "ai_can_auto_generate_strategy_code": False,
            "ai_can_promote_or_trade": False,
        },
        "findings": findings,
        "verdict": "PARTIAL_PIPELINE_NOT_SELF_IMPROVING_CLOSED_LOOP" if findings[1:] else "CLOSED_RESEARCH_LOOP",
        "required_next_controls": [
            "Add an explicit lifecycle ledger linking proposal_key to owner approval, prereg, spec, passport, result, independent audit and final verdict.",
            "Bind approvals to spec SHA256 and require experiment_preflight plus run_passport before launch.",
            "Run only bounded existing code automatically; AI-generated code remains review-and-test gated.",
            "Publish one fresh scheduler receipt per cycle and fail closed on stale status or nonzero independent audit."
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": result["verdict"], "findings": result["findings"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
