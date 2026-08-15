"""Audit whether the AI research loop is actually closed and continuously useful.

The audit is read-only.  It distinguishes healthy data/shadow collection from
the stronger claim that an AI idea can become a frozen, passported,
independently audited historical experiment without an unrecorded hand-off.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.experiment_lifecycle import LifecycleError, LifecycleLedger


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
    lifecycle_path = root / "runtime/research/experiment_lifecycle.jsonl"
    lifecycle_code_available = (root / "research_lab/experiment_lifecycle.py").is_file()
    lifecycle_integrity = False
    lifecycle_error: str | None = None
    lifecycle_summary: dict[str, Any] = {
        "records": 0,
        "experiments": {},
        "artifacts_verified": False,
    }
    if lifecycle_path.exists():
        try:
            lifecycle_summary = LifecycleLedger(
                lifecycle_path,
                project_root=root,
            ).summary(verify_artifacts=True)
            lifecycle_integrity = True
        except LifecycleError as exc:
            lifecycle_error = str(exc)
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
    lifecycle_experiments = lifecycle_summary.get("experiments") or {}
    lifecycle_terminal = sum(bool(item.get("terminal")) for item in lifecycle_experiments.values())
    lifecycle_approved = sum(
        "OWNER_APPROVED" in (item.get("stages") or [])
        for item in lifecycle_experiments.values()
    )
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
    if lifecycle_code_available and not lifecycle_path.exists():
        findings.append("hash_chained_lifecycle_control_available_but_not_yet_used")
    elif lifecycle_path.exists() and not lifecycle_integrity:
        findings.append("lifecycle_ledger_integrity_failed")
    elif lifecycle_path.exists() and lifecycle_integrity and not lifecycle_experiments:
        findings.append("lifecycle_ledger_valid_but_empty")
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
        "lifecycle": {
            "control_code_available": lifecycle_code_available,
            "ledger_present": lifecycle_path.exists(),
            "integrity_pass": lifecycle_integrity,
            "integrity_error": lifecycle_error,
            "records": int(lifecycle_summary.get("records") or 0),
            "experiments": len(lifecycle_experiments),
            "owner_approved_experiments": lifecycle_approved,
            "terminal_experiments": lifecycle_terminal,
            "artifacts_verified": bool(lifecycle_summary.get("artifacts_verified")),
        },
        "capabilities": {
            "ai_can_propose_complete_falsifiable_cards": True,
            "approved_existing_specs_can_be_executed_research_only": True,
            "idea_to_runnable_experiment_is_fully_automatic": bridge_closed,
            "approval_is_content_hash_bound": approvals_hash_bound,
            "hash_bound_lifecycle_control_is_implemented": lifecycle_code_available,
            "ai_can_auto_generate_strategy_code": False,
            "ai_can_promote_or_trade": False,
        },
        "findings": findings,
        "verdict": "PARTIAL_PIPELINE_NOT_SELF_IMPROVING_CLOSED_LOOP" if findings[1:] else "CLOSED_RESEARCH_LOOP",
        "required_next_controls": [
            "Route the next owner-approved idea through the hash-chained lifecycle ledger from idea through final decision.",
            "Migrate legacy name-only approvals only after owner re-approval of their current content hashes.",
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
