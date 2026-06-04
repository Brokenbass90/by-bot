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
DIAG_LOG_CANDIDATES = (
    ROOT / "runtime" / "live.out",
    ROOT / "runtime" / "bot.log",
    ROOT / "logs" / "bot.log",
)


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


def _current_counter_epoch(lines: list[str]) -> list[str]:
    """Keep only the latest monotonic counter epoch from append-only live.out."""
    if len(lines) < 2:
        return lines
    reset_keys = (
        "detect_call",
        "detect_gate_on",
        "ws_connect",
        "flat_try",
        "att1_try",
        "asm1_try",
        "midterm_try",
        "sloped_try",
        "breakdown_try",
    )
    start_idx = 0
    prev = _parse_diag(lines[0])
    for idx, line in enumerate(lines[1:], start=1):
        cur = _parse_diag(line)
        if any(int(prev.get(key, 0)) > 0 and int(cur.get(key, 0)) < int(prev.get(key, 0)) for key in reset_keys):
            start_idx = idx
        prev = cur
    return lines[start_idx:]


def _recent_file_lines(path: Path, *, max_bytes: int = 2_000_000, max_lines: int = 5000) -> list[str]:
    try:
        if not path.exists() or not path.is_file():
            return []
        size = int(path.stat().st_size)
        with path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(max(0, size - max_bytes))
            raw = fh.read()
        text = raw.decode("utf-8", errors="ignore")
        return text.splitlines()[-max_lines:]
    except Exception:
        return []


def _collect_diag_lines(since_hours: int) -> tuple[list[str], dict[str, int]]:
    max_age_sec = max(1, int(since_hours)) * 3600 + 900
    now_ts = datetime.now(timezone.utc).timestamp()
    max_lines = max(1000, min(12000, int(since_hours) * 300))
    out: list[str] = []
    source_counts: Counter[str] = Counter()
    seen: set[str] = set()

    # systemd/journal can be unavailable or omit stdout on some server setups.
    # The live process always mirrors its pulse diagnostics into runtime/live.out.
    for path in DIAG_LOG_CANDIDATES:
        try:
            age_sec = now_ts - float(path.stat().st_mtime)
        except Exception:
            continue
        if age_sec > max_age_sec:
            continue
        for line in _recent_file_lines(path, max_lines=max_lines):
            if "diag " not in line:
                continue
            clean = line.strip()
            if clean in seen:
                continue
            seen.add(clean)
            out.append(clean)
            source_counts[str(path.relative_to(ROOT))] += 1
    if out:
        return out, dict(source_counts)

    since_expr = f"{max(1, int(since_hours))} hours ago"
    cmd = ["journalctl", "-u", "bybot", "--since", since_expr, "--no-pager"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout:
            lines = [line.strip() for line in proc.stdout.splitlines() if "diag " in line]
            if lines:
                return lines, {"journalctl": len(lines)}
    except Exception:
        pass

    return [], {}


def _latest_pulse_state(lines: list[str]) -> dict[str, Any]:
    for line in reversed(lines):
        if "[pulse]" not in line:
            continue
        state: dict[str, Any] = {}
        for key in ("trade_on", "dry_run", "ws_guard"):
            m = re.search(rf"\b{key}=([01])\b", line)
            if m:
                state[key] = int(m.group(1))
        m = re.search(r"\bdisabled=([^ ]+)", line)
        if m:
            state["disabled"] = m.group(1)
        return state
    return {}


def _top_diag_keys(diag: dict[str, int], prefix: str, *, limit: int = 3) -> list[tuple[str, int]]:
    pairs = [
        (str(key), int(value))
        for key, value in diag.items()
        if str(key).startswith(prefix) and int(value) > 0
    ]
    pairs.sort(key=lambda item: (-item[1], item[0]))
    return pairs[:limit]


def _top_diag_keys_excluding(
    diag: dict[str, int],
    prefix: str,
    excluded: set[str],
    *,
    limit: int = 3,
) -> list[tuple[str, int]]:
    pairs = [
        (str(key), int(value))
        for key, value in diag.items()
        if str(key).startswith(prefix) and str(key) not in excluded and int(value) > 0
    ]
    pairs.sort(key=lambda item: (-item[1], item[0]))
    return pairs[:limit]


def _fmt_top_pairs(pairs: list[tuple[str, int]]) -> str:
    if not pairs:
        return "-"
    return ",".join(f"{key}={value}" for key, value in pairs)


def _entry_rate(entry: int, tries: int) -> float:
    if tries <= 0:
        return 0.0
    return float(entry) / float(tries)


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

    raw_diag_lines, diag_sources = _collect_diag_lines(since_hours)
    diag_lines = _current_counter_epoch(raw_diag_lines)
    diag = _diag_delta(diag_lines)
    pulse_state = _latest_pulse_state(diag_lines)

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
    elif (
        _safe_int(pulse_state.get("trade_on"), 0) == 1
        and _safe_int(pulse_state.get("dry_run"), 1) == 0
        and _safe_int(pulse_state.get("ws_guard"), 1) == 0
        and str(pulse_state.get("disabled") or "").lower() in {"false", "0", "none", ""}
    ):
        _add_finding(
            findings,
            "info",
            "Foundation is open; entry blockers are inside sleeves",
            f"trade_on={pulse_state.get('trade_on')}, dry_run={pulse_state.get('dry_run')}, ws_guard={pulse_state.get('ws_guard')}, allocator_status={alloc_status or '-'}",
        )

    flat_try = _safe_int(diag.get("flat_try"), 0)
    flat_entry = _safe_int(diag.get("flat_entry"), 0)
    flat_no_signal = _safe_int(diag.get("flat_no_signal"), 0)
    flat_same_bar = _safe_int(diag.get("flat_ns_same_bar"), 0)
    flat_touch = _safe_int(diag.get("flat_ns_touch"), 0)
    flat_top_reasons = _top_diag_keys(diag, "flat_ns_", limit=4)
    flat_eval_reasons = _top_diag_keys_excluding(diag, "flat_ns_", {"flat_ns_same_bar"}, limit=4)
    flat_eval_no_signal = max(0, flat_no_signal - flat_same_bar)
    if flat_try > 0 and flat_entry == 0:
        dominant_reason = flat_eval_reasons[0][0].removeprefix("flat_ns_") if flat_eval_reasons else "duplicate_bar"
        flat_severity = "warn" if flat_eval_no_signal > 0 else "info"
        flat_summary = (
            "Flat sleeve is alive but not converting into entries"
            if flat_eval_no_signal > 0
            else "Flat is waiting for the next closed signal candle"
        )
        _add_finding(
            findings,
            flat_severity,
            flat_summary,
            f"flat_try={flat_try}, flat_entry=0, flat_no_signal={flat_no_signal}, evaluated_no_signal={flat_eval_no_signal}, duplicate_bar={flat_same_bar}, dominant_evaluated_reason={dominant_reason}, eval_reasons={_fmt_top_pairs(flat_eval_reasons)}",
        )
        if flat_eval_reasons:
            _add_action(
                actions,
                "Use closed-bar flat telemetry before changing ARF1 thresholds",
                "Duplicate-bar noise is expected for 60m logic; the real tuning input is the evaluated no-signal reason distribution.",
            )
        else:
            _add_action(
                actions,
                "Wait for the next closed flat signal candle",
                "Recent flat attempts were mostly duplicate-bar checks, so there is not enough evaluated-bar evidence yet.",
            )

    sleeve_specs = [
        ("att1", "ATT1"),
        ("asm1", "ASM1"),
        ("midterm", "Midterm"),
    ]
    for prefix, label in sleeve_specs:
        tries = _safe_int(diag.get(f"{prefix}_try"), 0)
        entry = _safe_int(diag.get(f"{prefix}_entry"), 0)
        no_signal = _safe_int(diag.get(f"{prefix}_no_signal"), 0)
        top_reasons = _top_diag_keys(diag, f"{prefix}_ns_", limit=4)
        reason_txt = f", reasons={_fmt_top_pairs(top_reasons)}" if top_reasons else ""
        if tries > 0 and entry == 0 and no_signal >= max(3, int(tries * 0.9)):
            _add_finding(
                findings,
                "warn",
                f"{label} is scanning but every recent attempt is no_signal",
                f"{prefix}_try={tries}, {prefix}_entry=0, {prefix}_no_signal={no_signal}, entry_rate={_entry_rate(entry, tries):.2%}{reason_txt}",
            )
            if top_reasons:
                _add_action(
                    actions,
                    f"Review dominant {label} no_signal filter",
                    "The live telemetry now has filter-level attribution; compare the dominant blocker with backtest assumptions before changing thresholds.",
                )
            else:
                _add_action(
                    actions,
                    f"Add grouped no_signal reasons for {label}",
                    "The aggregate counter proves conversion failure, but the live telemetry still needs filter-level attribution.",
                )

    for prefix, label in (("sloped", "Sloped"), ("breakdown", "Breakdown")):
        sched = _safe_int(diag.get(f"{prefix}_sched"), 0)
        tries = _safe_int(diag.get(f"{prefix}_try"), 0)
        entry = _safe_int(diag.get(f"{prefix}_entry"), 0)
        cooldown = _safe_int(diag.get(f"{prefix}_skip_cooldown"), 0)
        symbol_lock = _safe_int(diag.get(f"{prefix}_skip_symbol_lock"), 0)
        if sched > 0 and entry == 0 and cooldown >= max(5, tries):
            _add_finding(
                findings,
                "warn",
                f"{label} is mostly being consumed by cooldown gates",
                f"{prefix}_sched={sched}, {prefix}_try={tries}, {prefix}_entry=0, {prefix}_skip_cooldown={cooldown}, {prefix}_skip_symbol_lock={symbol_lock}",
            )
            _add_action(
                actions,
                f"Check {label} cooldown against bar cadence and setup scanner",
                "Cooldown dominance can create a live/backtest frequency mismatch even when allocator and router are open.",
            )

    ivb1_try = _safe_int(diag.get("ivb1_try"), 0)
    ivb1_signal = _safe_int(diag.get("ivb1_signal"), 0)
    ivb1_shadow_signal = _safe_int(diag.get("ivb1_shadow_signal"), 0)
    ivb1_entry = _safe_int(diag.get("ivb1_entry"), 0)
    ivb1_no_breakout = _safe_int(diag.get("ivb1_ns_no_breakout"), 0)
    ivb1_impulse_body = _safe_int(diag.get("ivb1_ns_impulse_body"), 0)
    ivb1_other = _safe_int(diag.get("ivb1_ns_other"), 0)
    if ivb1_shadow_signal > 0:
        _add_finding(
            findings,
            "info",
            "IVB1 telemetry shadow is observing valid signals without capital",
            f"ivb1_try={ivb1_try}, ivb1_signal={ivb1_signal}, ivb1_shadow_signal={ivb1_shadow_signal}, ivb1_entry=0",
        )
    elif ivb1_try > 0 and ivb1_entry == 0:
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
    headline_item = max(
        findings,
        key=lambda item: severity_rank.get(str(item.get("severity") or "info"), 1),
        default={"summary": "Self-audit complete"},
    )
    headline = str(headline_item.get("summary") or "Self-audit complete")

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
            "pulse_trade_on": pulse_state.get("trade_on"),
            "pulse_dry_run": pulse_state.get("dry_run"),
            "pulse_disabled": pulse_state.get("disabled"),
            "pulse_ws_guard": pulse_state.get("ws_guard"),
            "alpaca_monthly_status": monthly.get("advisory_status"),
            "alpaca_intraday_open_positions": intraday_open,
        },
        "diag_window": {
            "raw_diag_line_count": len(raw_diag_lines),
            "diag_line_count": len(diag_lines),
            "diag_sources": diag_sources,
            "flat_try": flat_try,
            "flat_entry": flat_entry,
            "flat_no_signal": flat_no_signal,
            "flat_evaluated_no_signal": flat_eval_no_signal,
            "flat_ns_same_bar": flat_same_bar,
            "flat_ns_touch": flat_touch,
            "flat_top_reasons": dict(flat_top_reasons),
            "flat_evaluated_reasons": dict(flat_eval_reasons),
            "att1_try": _safe_int(diag.get("att1_try"), 0),
            "att1_entry": _safe_int(diag.get("att1_entry"), 0),
            "att1_no_signal": _safe_int(diag.get("att1_no_signal"), 0),
            "att1_top_reasons": dict(_top_diag_keys(diag, "att1_ns_", limit=6)),
            "asm1_try": _safe_int(diag.get("asm1_try"), 0),
            "asm1_entry": _safe_int(diag.get("asm1_entry"), 0),
            "asm1_no_signal": _safe_int(diag.get("asm1_no_signal"), 0),
            "asm1_top_reasons": dict(_top_diag_keys(diag, "asm1_ns_", limit=6)),
            "midterm_try": _safe_int(diag.get("midterm_try"), 0),
            "midterm_entry": _safe_int(diag.get("midterm_entry"), 0),
            "midterm_no_signal": _safe_int(diag.get("midterm_no_signal"), 0),
            "midterm_top_reasons": dict(_top_diag_keys(diag, "midterm_ns_", limit=6)),
            "sloped_sched": _safe_int(diag.get("sloped_sched"), 0),
            "sloped_try": _safe_int(diag.get("sloped_try"), 0),
            "sloped_entry": _safe_int(diag.get("sloped_entry"), 0),
            "sloped_skip_cooldown": _safe_int(diag.get("sloped_skip_cooldown"), 0),
            "breakdown_sched": _safe_int(diag.get("breakdown_sched"), 0),
            "breakdown_try": _safe_int(diag.get("breakdown_try"), 0),
            "breakdown_entry": _safe_int(diag.get("breakdown_entry"), 0),
            "breakdown_skip_cooldown": _safe_int(diag.get("breakdown_skip_cooldown"), 0),
            "ivb1_try": ivb1_try,
            "ivb1_signal": ivb1_signal,
            "ivb1_shadow_signal": ivb1_shadow_signal,
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
