#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.operator_snapshot import build_operator_snapshot  # noqa: E402


OUT_JSON = ROOT / "runtime" / "project_doctor" / "latest.json"
OUT_TXT = ROOT / "runtime" / "project_doctor" / "latest.txt"

LOCAL_ONLY_DIR_PREFIXES = (
    "logs/",
    "runtime/",
)
LOCAL_ONLY_FILES = {
    "configs/web_config.json",
}


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _git_dirty(root: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    out: list[str] = []
    for raw in proc.stdout.splitlines():
        if not raw.strip():
            continue
        path = raw[3:].strip() if len(raw) > 3 else raw.strip()
        out.append(path)
    return out


def _nonlocal_dirty(paths: list[str]) -> list[str]:
    out: list[str] = []
    for path in paths:
        norm = path.replace("\\", "/")
        if norm in LOCAL_ONLY_FILES:
            continue
        if any(norm.startswith(prefix) for prefix in LOCAL_ONLY_DIR_PREFIXES):
            continue
        out.append(norm)
    return out


def _load_health_entries(root: Path) -> dict[str, dict[str, Any]]:
    data = _load_json(root / "configs" / "strategy_health.json", {})
    entries = data.get("strategies", data) if isinstance(data, dict) else {}
    if not isinstance(entries, dict):
        return {}
    return {str(k): (v if isinstance(v, dict) else {}) for k, v in entries.items()}


def _load_policy_sleeves(root: Path) -> list[dict[str, Any]]:
    data = _load_json(root / "configs" / "portfolio_allocator_policy.json", {})
    sleeves = data.get("sleeves", []) if isinstance(data, dict) else []
    return [s for s in sleeves if isinstance(s, dict)]


def _count_file_lines(path: Path) -> int:
    try:
        return sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore"))
    except Exception:
        return 0


def _count_chat_messages(path: Path) -> int:
    data = _load_json(path, [])
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        if isinstance(data.get("messages"), list):
            return len(data["messages"])
        if isinstance(data.get("history"), list):
            return len(data["history"])
    return 0


def _risk_mult_for_regime(sleeve: dict[str, Any], regime: str) -> float:
    by_regime = sleeve.get("base_risk_mult_by_regime") or {}
    try:
        return float(by_regime.get(regime, 0.0) or 0.0)
    except Exception:
        return 0.0


def _add_finding(findings: list[dict[str, str]], severity: str, summary: str, detail: str) -> None:
    findings.append(
        {
            "severity": severity,
            "summary": summary,
            "detail": detail,
        }
    )


def _add_action(actions: list[dict[str, str]], summary: str, rationale: str) -> None:
    actions.append(
        {
            "summary": summary,
            "rationale": rationale,
        }
    )


def build_project_doctor(root: Path) -> dict[str, Any]:
    snapshot = build_operator_snapshot(root)
    heartbeat = dict(snapshot.get("heartbeat") or {})
    control_plane = dict(snapshot.get("control_plane") or {})
    allocator = dict(control_plane.get("allocator") or {})
    regime = dict(control_plane.get("regime") or {})
    nightly = dict(snapshot.get("nightly_research") or {})

    health_entries = _load_health_entries(root)
    policy_sleeves = _load_policy_sleeves(root)
    status_counts = Counter(
        str(v.get("status", "UNKNOWN")).upper()
        for v in health_entries.values()
        if isinstance(v, dict)
    )

    current_regime = str(regime.get("regime") or "").strip() or "unknown"
    enabled_sleeves = list(allocator.get("enabled_sleeves") or [])
    degraded_kind = str(allocator.get("degraded_kind") or "none")

    live_ready: list[str] = []
    watch_candidates: list[str] = []
    paused_research: list[str] = []
    policy_missing_health: list[str] = []
    active_repair_candidates: list[str] = []

    for sleeve in policy_sleeves:
        sleeve_name = str(sleeve.get("name") or "")
        strategy_names = [str(x) for x in (sleeve.get("strategy_names") or []) if str(x)]
        if not strategy_names:
            continue
        statuses = []
        for strategy_name in strategy_names:
            entry = health_entries.get(strategy_name)
            if not entry:
                policy_missing_health.append(f"{sleeve_name}:{strategy_name}")
                continue
            statuses.append(str(entry.get("status", "UNKNOWN")).upper())
        if not statuses:
            continue
        best_status = statuses[0]
        regime_risk = _risk_mult_for_regime(sleeve, current_regime)
        if best_status == "OK":
            live_ready.append(sleeve_name)
        elif best_status == "WATCH":
            watch_candidates.append(sleeve_name)
            if regime_risk > 0:
                active_repair_candidates.append(sleeve_name)
        elif best_status == "PAUSE":
            paused_research.append(sleeve_name)

    git_dirty = _git_dirty(root)
    nonlocal_dirty = _nonlocal_dirty(git_dirty)
    ai_memory_lines = _count_file_lines(root / "runtime" / "ai_operator" / "memory.jsonl")
    shared_chat_messages = _count_chat_messages(root / "data" / "deepseek_chat.json")

    findings: list[dict[str, str]] = []
    actions: list[dict[str, str]] = []

    hb_age = int(float(heartbeat.get("age_sec") or 0) or 0)
    if hb_age > 180:
        _add_finding(findings, "critical", "Heartbeat is stale", f"heartbeat_age_sec={hb_age}")
        _add_action(actions, "Repair the bot process before trusting research", "Runtime truth is stale.")

    if degraded_kind == "broken":
        _add_finding(findings, "critical", "Allocator degraded due to a real control-plane problem", str(allocator))
        _add_action(actions, "Fix allocator/router inputs first", "Portfolio risk truth is broken.")
    elif degraded_kind == "protective_overlap":
        _add_finding(
            findings,
            "info",
            "Allocator degrade is protective, not broken",
            f"enabled_sleeves={','.join(enabled_sleeves) or '-'}",
        )

    if len(live_ready) < 3:
        _add_finding(
            findings,
            "warn",
            "Too few sleeves are currently marked live-ready",
            f"live_ready_count={len(live_ready)} live_ready={','.join(live_ready) or '-'}",
        )
        _add_action(
            actions,
            "Promote the next sleeves only after long-horizon confirmation",
            "The portfolio still depends on a narrow live-ready core.",
        )

    if active_repair_candidates:
        _add_finding(
            findings,
            "info",
            "There are watch-stage candidates with non-zero regime weight",
            f"candidates={','.join(active_repair_candidates)} regime={current_regime}",
        )
        _add_action(
            actions,
            "Focus the next confirmations on watch-stage sleeves first",
            "They are closest to becoming portfolio add-ons.",
        )

    if paused_research:
        _add_finding(
            findings,
            "info",
            "Research backlog remains large",
            f"paused_research_count={len(paused_research)}",
        )

    if policy_missing_health:
        _add_finding(
            findings,
            "warn",
            "Policy includes sleeves without matching health entries",
            ",".join(policy_missing_health[:12]),
        )
        _add_action(
            actions,
            "Keep policy and health in sync",
            "Missing health rows create lying allocator/runtime behavior.",
        )

    if nonlocal_dirty:
        _add_finding(
            findings,
            "warn",
            "Project has meaningful uncommitted changes",
            ",".join(nonlocal_dirty[:12]),
        )
        _add_action(
            actions,
            "Commit or intentionally park meaningful local changes",
            "A living project should not hide important fixes in a dirty tree.",
        )

    if ai_memory_lines > 30 or shared_chat_messages > 30:
        _add_finding(
            findings,
            "warn",
            "AI context may be drifting toward stale memory again",
            f"memory_lines={ai_memory_lines}, shared_chat_messages={shared_chat_messages}",
        )
        _add_action(
            actions,
            "Prune or rotate shared AI memory more aggressively",
            "Truthful operator behavior depends on bounded context.",
        )

    nightly_state = str(nightly.get("state") or "")
    active_process_count = int(nightly.get("active_process_count") or 0)
    proposed_count = int(nightly.get("proposed_count") or 0)
    if nightly_state == "ok" and active_process_count <= 0 and proposed_count > 0:
        _add_finding(
            findings,
            "info",
            "Nightly research queue is idle with queued work still waiting",
            f"proposed={proposed_count}",
        )
        _add_action(
            actions,
            "Review why the queue is not launching proposed work",
            "Idle research slows the self-improving loop.",
        )

    if not findings:
        _add_finding(findings, "ok", "Project doctor found no immediate structural gaps", "Core truth layers look consistent.")

    severity_rank = {"ok": 0, "info": 1, "warn": 2, "critical": 3}
    highest = max(severity_rank.get(str(item.get("severity") or "info"), 1) for item in findings)
    inv = {v: k for k, v in severity_rank.items()}

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "headline": findings[0]["summary"],
        "highest_severity": inv.get(highest, "info"),
        "runtime": {
            "heartbeat_age_sec": hb_age,
            "open_trades": heartbeat.get("open_trades"),
            "regime": current_regime,
            "allocator_status": allocator.get("status"),
            "degraded_kind": degraded_kind,
            "enabled_sleeves": enabled_sleeves,
        },
        "strategy_status": {
            "counts": dict(status_counts),
            "live_ready_sleeves": sorted(set(live_ready)),
            "watch_candidates": sorted(set(watch_candidates)),
            "paused_research": sorted(set(paused_research)),
            "policy_missing_health": sorted(set(policy_missing_health)),
        },
        "project_hygiene": {
            "dirty_files": git_dirty,
            "meaningful_dirty_files": nonlocal_dirty,
            "ai_memory_lines": ai_memory_lines,
            "shared_chat_messages": shared_chat_messages,
            "nightly_research_state": nightly_state,
            "nightly_active_process_count": active_process_count,
            "nightly_proposed_count": proposed_count,
        },
        "findings": findings,
        "actions": actions,
    }


def _format_text(report: dict[str, Any]) -> str:
    lines = [
        "project doctor",
        f"generated_at_utc={report.get('generated_at_utc')}",
        f"highest_severity={report.get('highest_severity')}",
        f"headline={report.get('headline')}",
        "",
        "[runtime]",
    ]
    for key, value in dict(report.get("runtime") or {}).items():
        lines.append(f"{key}={value}")
    lines.extend(["", "[strategy_status]"])
    strategy_status = dict(report.get("strategy_status") or {})
    counts = dict(strategy_status.get("counts") or {})
    lines.append(f"counts={counts}")
    for key in ("live_ready_sleeves", "watch_candidates", "paused_research", "policy_missing_health"):
        lines.append(f"{key}={strategy_status.get(key)}")
    lines.extend(["", "[project_hygiene]"])
    for key, value in dict(report.get("project_hygiene") or {}).items():
        lines.append(f"{key}={value}")
    lines.extend(["", "[findings]"])
    for item in list(report.get("findings") or []):
        lines.append(f"- {item.get('severity')}: {item.get('summary')} | {item.get('detail')}")
    lines.extend(["", "[actions]"])
    for item in list(report.get("actions") or []):
        lines.append(f"- {item.get('summary')} | {item.get('rationale')}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a structural project-doctor report from runtime + code/config truth.")
    ap.add_argument("--out-json", default=str(OUT_JSON))
    ap.add_argument("--out-txt", default=str(OUT_TXT))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    out_json = Path(args.out_json).expanduser()
    out_txt = Path(args.out_txt).expanduser()
    if not out_json.is_absolute():
        out_json = ROOT / out_json
    if not out_txt.is_absolute():
        out_txt = ROOT / out_txt

    report = build_project_doctor(ROOT)
    text = _format_text(report)

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    out_txt.write_text(text + "\n", encoding="utf-8")

    if not args.quiet:
        print(text)
        print("")
        print(f"saved_json={out_json}")
        print(f"saved_txt={out_txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
