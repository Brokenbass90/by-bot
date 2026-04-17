#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
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


OUT_JSON = ROOT / "runtime" / "self_audit" / "latest.json"
OUT_TXT = ROOT / "runtime" / "self_audit" / "latest.txt"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _parse_diag(line: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, value in re.findall(r"([a-z0-9_]+)=([0-9]+)", str(line or "")):
        out[key] = int(value)
    return out


def _diag_delta(lines: list[str]) -> dict[str, int]:
    if not lines:
        return {}
    parsed = [_parse_diag(line) for line in lines if "diag " in line]
    if not parsed:
        return {}
    delta: Counter[str] = Counter()
    prev = parsed[0]
    for cur in parsed[1:]:
        for key in set(prev) | set(cur):
            pv = int(prev.get(key, 0))
            cv = int(cur.get(key, 0))
            delta[key] += cv if cv < pv else (cv - pv)
        prev = cur
    if len(parsed) == 1:
        delta.update(parsed[0])
    return dict(delta)


def _collect_diag_lines(since_hours: int) -> list[str]:
    since_expr = f"{max(1, int(since_hours))} hours ago"
    cmd = ["journalctl", "-u", "bybot", "--since", since_expr, "--no-pager"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout:
            return [line.strip() for line in proc.stdout.splitlines() if "diag " in line]
    except Exception:
        pass

    bot_log = ROOT / "runtime" / "bot.log"
    try:
        if bot_log.exists():
            lines = bot_log.read_text(encoding="utf-8", errors="ignore").splitlines()
            return [line.strip() for line in lines[-1000:] if "diag " in line]
    except Exception:
        pass
    return []


def _add_finding(findings: list[dict[str, Any]], severity: str, summary: str, detail: str) -> None:
    findings.append(
        {
            "severity": severity,
            "summary": summary,
            "detail": detail,
        }
    )


def _add_action(actions: list[dict[str, Any]], summary: str, rationale: str) -> None:
    actions.append(
        {
            "summary": summary,
            "rationale": rationale,
        }
    )


def build_self_audit(root: Path, *, since_hours: int = 6) -> dict[str, Any]:
    snapshot = build_operator_snapshot(root)
    heartbeat = dict(snapshot.get("heartbeat") or {})
    control_plane = dict(snapshot.get("control_plane") or {})
    allocator = dict(control_plane.get("allocator") or {})
    regime = dict(control_plane.get("regime") or {})
    nightly = dict(snapshot.get("nightly_research") or {})
    alpaca = dict(snapshot.get("alpaca") or {})
    monthly = dict(alpaca.get("monthly") or {})
    intraday = dict(alpaca.get("intraday") or {})

    diag_lines = _collect_diag_lines(since_hours)
    diag = _diag_delta(diag_lines)

    findings: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    hb_age = heartbeat.get("age_sec")
    if hb_age is None or _safe_int(hb_age, 999999) > 180:
        _add_finding(
            findings,
            "critical",
            "Heartbeat stale or missing",
            f"heartbeat_age_sec={hb_age}; bot may be down or not updating runtime state.",
        )
        _add_action(actions, "Check bybot heartbeat/process first", "Stale heartbeat invalidates all later diagnostics.")

    alloc_status = str(allocator.get("status") or "").strip().lower()
    global_risk = _safe_float(allocator.get("global_risk_mult"), 0.0)
    if alloc_status and alloc_status != "ok":
        severity = "critical" if global_risk <= 0.0 else "warn"
        _add_finding(
            findings,
            severity,
            "Allocator is not fully open",
            f"status={alloc_status}, global_risk_mult={global_risk}, degraded_sleeves={','.join(allocator.get('degraded_sleeves') or []) or '-'}",
        )
        if global_risk <= 0.0:
            _add_action(actions, "Repair control-plane allocator", "Risk is effectively blocked right now.")
        else:
            _add_action(actions, "Treat allocator haircut as secondary", "Capital is reduced, but the bigger issue is still sleeve entry-rate.")

    flat_try = _safe_int(diag.get("flat_try"), 0)
    flat_entry = _safe_int(diag.get("flat_entry"), 0)
    flat_same_bar = _safe_int(diag.get("flat_ns_same_bar"), 0)
    flat_touch = _safe_int(diag.get("flat_ns_touch"), 0)
    if flat_try > 0 and flat_entry == 0:
        dominant_reason = "same_bar" if flat_same_bar >= flat_touch else "touch"
        _add_finding(
            findings,
            "warn",
            "Flat sleeve is alive but not converting into entries",
            f"flat_try={flat_try}, flat_entry=0, dominant_reason={dominant_reason}, flat_ns_same_bar={flat_same_bar}, flat_ns_touch={flat_touch}",
        )
        if flat_same_bar >= max(5, flat_touch):
            _add_action(
                actions,
                "Increase flat decision opportunities before loosening risk filters",
                "The dominant blocker is same-bar gating, so the next win is more quality bars/universe density, not weaker stops.",
            )
        else:
            _add_action(
                actions,
                "Retune flat touch/reject geometry",
                "The dominant blocker is the resistance touch itself, not risk or RSI.",
            )

    ivb1_try = _safe_int(diag.get("ivb1_try"), 0)
    ivb1_entry = _safe_int(diag.get("ivb1_entry"), 0)
    ivb1_no_breakout = _safe_int(diag.get("ivb1_ns_no_breakout"), 0)
    ivb1_impulse_body = _safe_int(diag.get("ivb1_ns_impulse_body"), 0)
    ivb1_other = _safe_int(diag.get("ivb1_ns_other"), 0)
    if ivb1_try > 0 and ivb1_entry == 0:
        if ivb1_other >= max(ivb1_no_breakout, ivb1_impulse_body):
            dominant = "other"
        elif ivb1_no_breakout >= ivb1_impulse_body:
            dominant = "no_breakout"
        else:
            dominant = "impulse_body"
        _add_finding(
            findings,
            "warn",
            "IVB1 is scanning but not reaching valid entry structure",
            f"ivb1_try={ivb1_try}, ivb1_entry=0, dominant_reason={dominant}, no_breakout={ivb1_no_breakout}, impulse_body={ivb1_impulse_body}, other={ivb1_other}",
        )
        _add_action(
            actions,
            "Use research to widen IVB1 frequency without breaking quality",
            "The next lever is universe/pattern calibration; allocator is not the main blocker here.",
        )

    elder_try = _safe_int(diag.get("elder_try"), 0)
    elder_entry = _safe_int(diag.get("elder_entry"), 0)
    if elder_try == 0 and elder_entry == 0:
        _add_finding(
            findings,
            "info",
            "Elder is still not a live sleeve",
            "Canonical rewrite is still in research territory; it should not be trusted as a production source of frequency yet.",
        )
        _add_action(
            actions,
            "Keep Elder in rewrite/research mode",
            "Do not spend live capital on Elder until annual validation produces stable trades and PF.",
        )

    monthly_status = str(monthly.get("advisory_status") or "")
    monthly_symbols = list(monthly.get("selected_symbols") or [])
    intraday_open = list(intraday.get("open_positions") or [])
    if monthly_status == "selected_current_cycle" and monthly_symbols:
        _add_finding(
            findings,
            "info",
            "Alpaca monthly has a fresh cycle selected",
            f"selected_symbols={','.join(monthly_symbols)}, earnings_blocked={','.join(monthly.get('earnings_blocked') or []) or '-'}",
        )
        _add_action(
            actions,
            "Leave monthly Alpaca stable through the paper window",
            "Fresh cycle selection is working; the next proof needed is clean paper-cycle persistence, not more logic churn.",
        )

    if intraday_open:
        _add_finding(
            findings,
            "info",
            "Alpaca intraday is actively holding paper risk",
            f"open_positions={','.join(intraday_open)}, mode={intraday.get('mode') or '-'}",
        )

    research_active = _safe_int(nightly.get("active_process_count"), 0)
    if research_active <= 0:
        _add_finding(
            findings,
            "info",
            "Slow server research queue is currently idle",
            f"nightly_state={nightly.get('state') or '-'}, proposed={nightly.get('proposed_count')}, blocked={nightly.get('blocked_count')}",
        )

    if not findings:
        _add_finding(
            findings,
            "ok",
            "No urgent blockers detected",
            "Foundation looks healthy and no critical trading blocker dominated the recent audit window.",
        )

    severity_rank = {"ok": 0, "info": 1, "warn": 2, "critical": 3}
    highest = max((severity_rank.get(str(item.get("severity") or "info"), 1) for item in findings), default=0)
    inv_rank = {value: key for key, value in severity_rank.items()}
    highest_severity = inv_rank.get(highest, "info")
    headline = str(findings[0].get("summary") or "Self-audit complete")

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "since_hours": int(since_hours),
        "headline": headline,
        "highest_severity": highest_severity,
        "snapshot": {
            "heartbeat_age_sec": heartbeat.get("age_sec"),
            "open_trades": heartbeat.get("open_trades"),
            "regime": regime.get("regime"),
            "allocator_status": allocator.get("status"),
            "global_risk_mult": allocator.get("global_risk_mult"),
            "alpaca_monthly_status": monthly.get("advisory_status"),
            "alpaca_intraday_open_positions": intraday_open,
        },
        "diag_window": {
            "diag_line_count": len(diag_lines),
            "flat_try": flat_try,
            "flat_entry": flat_entry,
            "flat_ns_same_bar": flat_same_bar,
            "flat_ns_touch": flat_touch,
            "ivb1_try": ivb1_try,
            "ivb1_entry": ivb1_entry,
            "ivb1_ns_no_breakout": ivb1_no_breakout,
            "ivb1_ns_impulse_body": ivb1_impulse_body,
            "ivb1_ns_other": ivb1_other,
            "elder_try": elder_try,
            "elder_entry": elder_entry,
        },
        "findings": findings,
        "actions": actions,
    }


def _format_text(report: dict[str, Any]) -> str:
    lines = [
        "self audit",
        f"generated_at_utc={report.get('generated_at_utc')}",
        f"since_hours={report.get('since_hours')}",
        f"highest_severity={report.get('highest_severity')}",
        f"headline={report.get('headline')}",
        "",
        "[snapshot]",
    ]
    for key, value in dict(report.get("snapshot") or {}).items():
        lines.append(f"{key}={value}")
    lines.extend(
        [
            "",
            "[diag_window]",
        ]
    )
    for key, value in dict(report.get("diag_window") or {}).items():
        lines.append(f"{key}={value}")
    lines.extend(["", "[findings]"])
    for item in list(report.get("findings") or []):
        lines.append(f"- {item.get('severity')}: {item.get('summary')} | {item.get('detail')}")
    lines.extend(["", "[actions]"])
    for item in list(report.get("actions") or []):
        lines.append(f"- {item.get('summary')} | {item.get('rationale')}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a slow self-audit report from snapshot + runtime diagnostics.")
    ap.add_argument("--since-hours", type=int, default=6)
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

    report = build_self_audit(ROOT, since_hours=max(1, int(args.since_hours)))
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
