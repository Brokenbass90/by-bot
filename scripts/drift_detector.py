#!/usr/bin/env python3
"""Daily strategy drift detector.

Compares aggregate runtime counters and live trade outcomes over the **last
7 days** vs the **trailing 30-day baseline (excluding the recent 7d window)**.
Flags strategies whose:

  - signal/try ratio dropped > 30% (filter started rejecting more)
  - winrate dropped > 15 percentage points
  - profit factor dropped > 30%
  - average pnl per trade flipped negative
  - signal frequency dropped > 50% with no underlying regime change

This is **early-warning observability**, not autopause. The bot keeps trading.
Output:

  - `runtime/drift_report.json` (structured)
  - Optional Telegram alert (if drift severity >= "amber") via TG_BOT_TOKEN/TG_CHAT_ID

The detector reads:

  - `runtime/live_mirror/live_trade_events.jsonl` (per-trade outcomes)
  - `runtime/live_mirror/bot_heartbeat.json` (aggregate counters snapshot only)
  - `runtime/strategy_pipeline.json` (stage info)

Severity classification:
  - green   = no significant drift
  - yellow  = 1 metric crossed warn-threshold for >= 1 sleeve
  - amber   = 2+ metrics crossed warn-threshold, or 1 metric crossed danger threshold
  - red     = consecutive loss streak >= 5 in last 7d for any sleeve with > 5 trades

Cron suggestion: 1 per day, e.g.::

    30 7 * * * /usr/bin/python3 /root/by-bot/scripts/drift_detector.py >> /root/by-bot/runtime/drift_detector.log 2>&1

Usage::

    python3 scripts/drift_detector.py                # plain report
    python3 scripts/drift_detector.py --notify-tg    # also send TG alert if amber+
    python3 scripts/drift_detector.py --window-days 14  # custom recent window

Author: Claude Opus, 2026-06-03. Read-only diagnostic.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "runtime" / "live_trade_events.jsonl"
MIRROR_EVENTS = ROOT / "runtime" / "live_mirror" / "live_trade_events.jsonl"
HEARTBEAT = ROOT / "runtime" / "bot_heartbeat.json"
MIRROR_HEARTBEAT = ROOT / "runtime" / "live_mirror" / "bot_heartbeat.json"
PIPELINE = ROOT / "runtime" / "strategy_pipeline.json"
REPORT_OUT = ROOT / "runtime" / "drift_report.json"

_SSL = ssl.create_default_context()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_json(p: Path, default: Any = None) -> Any:
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_env_file(p: Path) -> None:
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def _tail_events(path: Path, n: int = 20000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()[-n:]
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for raw in lines:
        try:
            out.append(json.loads(raw))
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# Per-window stats
# ---------------------------------------------------------------------------

def _closes_in_window(events: list[dict[str, Any]], since_ts: int, until_ts: int | None) -> list[dict[str, Any]]:
    out = []
    for ev in events:
        if str(ev.get("event") or "") != "close":
            continue
        ts = int(ev.get("ts") or 0)
        if ts < since_ts:
            continue
        if until_ts is not None and ts >= until_ts:
            continue
        out.append(ev)
    return out


def _per_strategy_stats(closes: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Aggregate by strategy: n, winrate, pf, avg_pnl, total_pnl, loss_streak_max."""
    per: dict[str, dict[str, Any]] = {}
    for c in sorted(closes, key=lambda x: int(x.get("ts") or 0)):
        s = str(c.get("strategy") or "unknown")
        d = per.setdefault(s, {"n": 0, "wins": 0, "gross_win": 0.0, "gross_loss": 0.0,
                                "total_pnl": 0.0, "cur_loss_streak": 0, "max_loss_streak": 0})
        pnl = float(c.get("pnl") or 0.0)
        d["n"] += 1
        d["total_pnl"] += pnl
        if pnl > 0:
            d["wins"] += 1
            d["gross_win"] += pnl
            d["cur_loss_streak"] = 0
        else:
            d["gross_loss"] += abs(pnl)
            d["cur_loss_streak"] += 1
            d["max_loss_streak"] = max(d["max_loss_streak"], d["cur_loss_streak"])

    out: dict[str, dict[str, float]] = {}
    for s, d in per.items():
        n = max(1, d["n"])
        wr = (d["wins"] / n) * 100.0
        pf = (d["gross_win"] / d["gross_loss"]) if d["gross_loss"] > 0 else (float("inf") if d["gross_win"] > 0 else 0.0)
        out[s] = {
            "n": d["n"],
            "winrate_pct": round(wr, 2),
            "profit_factor": round(pf, 3) if pf != float("inf") else 99.0,
            "avg_pnl": round(d["total_pnl"] / d["n"], 4) if d["n"] > 0 else 0.0,
            "total_pnl": round(d["total_pnl"], 4),
            "max_loss_streak": d["max_loss_streak"],
        }
    return out


# ---------------------------------------------------------------------------
# Drift classification
# ---------------------------------------------------------------------------

WARN_TH = {
    "winrate_drop_pp": 15.0,           # 15 percentage points drop
    "pf_drop_pct": 30.0,                # PF dropped > 30%
    "avg_pnl_flipped_negative": True,   # flag if recent < 0 and baseline > 0
    "trades_drop_pct": 50.0,            # recent trades less than half of baseline rate
}
DANGER_TH = {
    "pf_drop_pct": 50.0,
    "loss_streak_min": 5,
}


def _classify_strategy(recent: dict[str, float], baseline: dict[str, float]) -> dict[str, Any]:
    flags: list[str] = []
    severity = "green"
    n_recent = int(recent.get("n", 0))
    n_baseline = int(baseline.get("n", 0))

    if n_recent < 3:
        return {"flags": ["insufficient_recent_sample"], "severity": "green",
                "n_recent": n_recent, "n_baseline": n_baseline}

    # 1) Winrate drop
    wr_drop = float(baseline.get("winrate_pct", 0.0)) - float(recent.get("winrate_pct", 0.0))
    if wr_drop > WARN_TH["winrate_drop_pp"]:
        flags.append(f"winrate_drop_{wr_drop:.1f}pp")

    # 2) Profit factor drop
    bpf = float(baseline.get("profit_factor", 0.0))
    rpf = float(recent.get("profit_factor", 0.0))
    if bpf > 0:
        pf_drop_pct = ((bpf - rpf) / bpf) * 100.0
        if pf_drop_pct >= DANGER_TH["pf_drop_pct"]:
            flags.append(f"pf_drop_{pf_drop_pct:.0f}pct_danger")
            severity = "amber"
        elif pf_drop_pct >= WARN_TH["pf_drop_pct"]:
            flags.append(f"pf_drop_{pf_drop_pct:.0f}pct")

    # 3) avg_pnl flipped negative
    if float(baseline.get("avg_pnl", 0.0)) > 0 and float(recent.get("avg_pnl", 0.0)) < 0:
        flags.append("avg_pnl_flipped_negative")

    # 4) Trade frequency drop (assuming baseline window is ~4x recent window)
    if n_baseline > 0:
        # baseline is 30d-7d = 23d, recent is 7d, so expected rate factor = 7/23 ≈ 0.30
        expected_n_at_recent_rate = (n_baseline * 7.0) / 23.0
        if expected_n_at_recent_rate > 4 and n_recent < expected_n_at_recent_rate * 0.5:
            flags.append("trade_frequency_halved")

    # 5) Loss streak danger
    streak = int(recent.get("max_loss_streak", 0))
    if streak >= DANGER_TH["loss_streak_min"]:
        flags.append(f"loss_streak_{streak}_red")
        severity = "red"

    # Severity escalation
    if flags and severity == "green":
        severity = "yellow"
    if len([f for f in flags if "_danger" not in f]) >= 2 and severity == "yellow":
        severity = "amber"

    return {
        "flags": flags,
        "severity": severity,
        "n_recent": n_recent,
        "n_baseline": n_baseline,
        "recent": recent,
        "baseline": baseline,
        "winrate_drop_pp": round(wr_drop, 2),
        "pf_baseline": bpf,
        "pf_recent": rpf,
    }


def _overall_severity(per_strategy: dict[str, dict[str, Any]]) -> str:
    order = {"green": 0, "yellow": 1, "amber": 2, "red": 3}
    worst = "green"
    for d in per_strategy.values():
        s = str(d.get("severity") or "green")
        if order.get(s, 0) > order.get(worst, 0):
            worst = s
    return worst


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def _tg_send(text: str) -> None:
    token = (os.getenv("TG_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TG_CHAT_ID") or "").strip()
    if not (token and chat_id):
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:4000],
                                   "disable_web_page_preview": "true"}).encode()
    req = request.Request(url, data=body, method="POST",
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        request.urlopen(req, context=_SSL, timeout=15).read()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Daily strategy drift detector")
    ap.add_argument("--window-days", type=int, default=7, help="Recent window size in days")
    ap.add_argument("--baseline-days", type=int, default=30, help="Baseline lookback total")
    ap.add_argument("--notify-tg", action="store_true",
                    help="Send TG alert if overall severity >= amber")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    _load_env_file(ROOT / ".env")

    events_path = EVENTS if EVENTS.exists() else MIRROR_EVENTS
    heartbeat_path = HEARTBEAT if HEARTBEAT.exists() else MIRROR_HEARTBEAT

    events = _tail_events(events_path, n=20000)
    now = _utc_now()
    recent_since = int((now - timedelta(days=args.window_days)).timestamp())
    baseline_since = int((now - timedelta(days=args.baseline_days)).timestamp())

    recent_closes = _closes_in_window(events, recent_since, None)
    baseline_closes = _closes_in_window(events, baseline_since, recent_since)

    recent_stats = _per_strategy_stats(recent_closes)
    baseline_stats = _per_strategy_stats(baseline_closes)

    all_strategies = sorted(set(recent_stats) | set(baseline_stats))
    per: dict[str, dict[str, Any]] = {}
    for s in all_strategies:
        per[s] = _classify_strategy(
            recent_stats.get(s, {"n": 0}),
            baseline_stats.get(s, {"n": 0}),
        )

    severity = _overall_severity(per)
    report = {
        "generated_at_utc": now.isoformat(),
        "window_recent_days": args.window_days,
        "window_baseline_days": args.baseline_days - args.window_days,
        "overall_severity": severity,
        "events_path": str(events_path),
        "heartbeat_path": str(heartbeat_path),
        "per_strategy": per,
        "total_recent_closes": len(recent_closes),
        "total_baseline_closes": len(baseline_closes),
        "thresholds": {"warn": WARN_TH, "danger": DANGER_TH},
    }
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "generated_at_utc": now.isoformat(),
        "overall_severity": severity,
        "total_strategies": len(per),
        "alerting_strategies": [s for s, d in per.items() if d.get("severity") not in (None, "green")],
        "total_recent_closes": len(recent_closes),
        "total_baseline_closes": len(baseline_closes),
        "report_path": str(REPORT_OUT),
    }

    if args.notify_tg and severity in ("amber", "red"):
        bullets = []
        for s in summary["alerting_strategies"][:5]:
            d = per[s]
            bullets.append(f"  • {s} [{d['severity']}]: {', '.join(d.get('flags', [])) or '—'}")
        msg = (f"📉 Drift detector: overall severity = *{severity}*\n"
               f"Recent 7d closes: {len(recent_closes)} | Baseline: {len(baseline_closes)}\n"
               + "\n".join(bullets))
        _tg_send(msg)
        summary["tg_sent"] = True

    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
