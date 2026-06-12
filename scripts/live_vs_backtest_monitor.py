#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
live_vs_backtest_monitor.py — Phase 3 #2: Performance Degradation Detector
===========================================================================
Monitors per-strategy live P&L against backtest expectations.
When a strategy's rolling 30-day profit factor drops below
  (backtest_pf × DEGRADE_THRESHOLD)
it pauses the strategy (sets STRATEGY_X_RISK_MULT=0.0 in a pause env file)
and sends a Telegram alert.

Recovery: when the rolling PF recovers above
  (backtest_pf × RECOVER_THRESHOLD)
the pause is lifted and TG alert sent.

Output:
  runtime/strategy_health.json   — per-strategy health summary
  runtime/strategy_pause.env     — env overrides (risk=0.0 for degraded strategies)
  runtime/auto_apply_log.jsonl   — append pause/recover events (shared with auto_apply)

Usage:
  python3 scripts/live_vs_backtest_monitor.py           # one-shot
  python3 scripts/live_vs_backtest_monitor.py --dry-run # print only

Cron (every 4 hours):
  0 */4 * * * cd /root/by-bot && python3 scripts/live_vs_backtest_monitor.py >> logs/strategy_monitor.log 2>&1

Env vars:
  MONITOR_DEGRADE_THRESHOLD   float, default 0.60  (live PF < backtest × this → pause)
  MONITOR_RECOVER_THRESHOLD   float, default 0.80  (live PF > backtest × this → recover)
  MONITOR_MIN_TRADES          int,   default 10    (min live trades to evaluate)
  MONITOR_EMERGENCY_MIN_TRADES int,  default 5     (min trades for live-bleed emergency stop)
  MONITOR_EMERGENCY_PF        float, default 0.20  (pause below this PF even before full sample)
  MONITOR_EMERGENCY_NET_PNL   float, default -0.50 (pause if rolling net PnL is worse)
  MONITOR_ROLLING_DAYS        int,   default 30    (rolling window in days)
  MONITOR_BACKTEST_PF         json string, e.g. '{"alt_resistance_fade_v1":1.4}'
                               fallback PF expectations per strategy. If not set,
                               uses built-in defaults table.
  TG_TOKEN / TG_CHAT_ID       for alerts (optional)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.request
import ssl
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_HEALTH = ROOT / "runtime" / "strategy_health.json"
OUTPUT_PAUSE  = ROOT / "runtime" / "strategy_pause.env"
LOG_JSONL     = ROOT / "runtime" / "auto_apply_log.jsonl"

OUTPUT_HEALTH.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Backtest reference PF table (override with MONITOR_BACKTEST_PF env var)
# Keep in sync with STRATEGY_STATUS_20260419.md
# ---------------------------------------------------------------------------
_DEFAULT_BACKTEST_PF: Dict[str, float] = {
    # Production strategies (current portfolio baseline PF=1.591 — 2026-05-26 audit)
    "alt_resistance_fade_v1":     1.40,
    "alt_sloped_channel_v1":      1.30,
    "alt_support_bounce_v1":      1.30,
    "alt_range_scalp_v1":         1.25,
    "impulse_volume_breakout_v1": 1.48,
    "alt_inplay_breakdown_v1":    1.35,
    "btc_eth_midterm_pullback":   1.30,
    "btc_eth_midterm_v3":         1.30,
    # Live strategy labels emitted by smart_pump_reversal_bot.py
    "flat_resistance_fade":       1.40,
    "att1_trendline_touch":       1.25,
    # Awaiting promotion via sweep (2026-05-27)
    "alt_trendline_touch_v1":     1.25,
    "alt_bear_regime_continuation_v1": 1.30,   # 90d showed PF 4.80, conservative ref
    "alt_slope_break_v1":         1.25,
    "elder_triple_screen_v2":     1.20,
    "elder_triple_screen_v3":     1.20,
    # Lower confidence (waiting for sweep validation)
    "inplay_breakout":            1.20,
    "alt_horizontal_break_v1":    1.20,
    "session_open_breakout_v1":   1.20,
    "funding_rate_reversion_v1":  1.20,
    "liquidation_cascade_entry_v1": 1.20,
    "sloped_resistance_choch_v1": 1.20,
    "micro_scalper_v1":           1.20,
}

# ---------------------------------------------------------------------------
# Risk env key per strategy name (what to zero-out when pausing)
# ---------------------------------------------------------------------------
_STRATEGY_RISK_KEY: Dict[str, str] = {
    "alt_resistance_fade_v1":         "FLAT_RISK_MULT",
    "alt_sloped_channel_v1":          "SLOPED_RISK_MULT",
    "alt_support_bounce_v1":          "BOUNCE1_RISK_MULT",
    "alt_range_scalp_v1":             "RANGE_RISK_MULT",
    "impulse_volume_breakout_v1":     "IVB1_RISK_MULT",
    "alt_inplay_breakdown_v1":        "BREAKDOWN_RISK_MULT",
    "flat_resistance_fade":           "FLAT_RISK_MULT",
    "att1_trendline_touch":           "ATT1_RISK_MULT",
    "inplay_breakout":                "BREAKOUT_RISK_MULT",
    "alt_inplay_breakdown_v2":        "BREAKDOWN2_RISK_MULT",
    "elder_triple_screen_v2":         "ELDER_RISK_MULT",
    "elder_triple_screen_v3":         "ETS3_RISK_MULT",
    "alt_trendline_touch_v1":         "ATT1_RISK_MULT",
    "alt_slope_break_v1":             "ASB1_RISK_MULT",        # added 2026-05-27
    "alt_bear_regime_continuation_v1":"BRC1_RISK_MULT",        # added 2026-05-27
    "btc_eth_midterm_pullback":       "MIDTERM_RISK_MULT",     # added 2026-05-27
    "btc_eth_midterm_v3":             "MIDTERM_RISK_MULT",     # added 2026-05-27
    "alt_horizontal_break_v1":        "HZBO1_RISK_MULT",
    "session_open_breakout_v1":       "SOB1_RISK_MULT",
    "funding_rate_reversion_v1":      "FR_RISK_MULT",
    "liquidation_cascade_entry_v1":   "LC_RISK_MULT",
    "sloped_resistance_choch_v1":     "SLOPE_CHOCH_RISK_MULT",
    "micro_scalper_v1":               "MSCALP_RISK_MULT",
}

# Current live bot uses _risk_mult_or_pause for most sleeve risk multipliers and
# hot-applies runtime/strategy_pause.env. Keep this map aligned with emitted live
# strategy labels; otherwise a bleeding sleeve can hide behind "insufficient_data".

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEGRADE_THRESHOLD = float(os.getenv("MONITOR_DEGRADE_THRESHOLD", "0.60"))
RECOVER_THRESHOLD = float(os.getenv("MONITOR_RECOVER_THRESHOLD", "0.80"))
MIN_TRADES        = int(os.getenv("MONITOR_MIN_TRADES", "10"))
EMERGENCY_MIN_TRADES = int(os.getenv("MONITOR_EMERGENCY_MIN_TRADES", "5"))
EMERGENCY_PF      = float(os.getenv("MONITOR_EMERGENCY_PF", "0.20"))
EMERGENCY_NET_PNL = float(os.getenv("MONITOR_EMERGENCY_NET_PNL", "-0.50"))
ROLLING_DAYS      = int(os.getenv("MONITOR_ROLLING_DAYS", "30"))
TG_TOKEN          = os.getenv("TG_TOKEN", "")
TG_CHAT_ID        = os.getenv("TG_CHAT_ID", os.getenv("TG_CHAT", ""))

_custom_pf = os.getenv("MONITOR_BACKTEST_PF", "")
if _custom_pf:
    try:
        _DEFAULT_BACKTEST_PF.update(json.loads(_custom_pf))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tg(text: str) -> None:
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        payload = json.dumps({
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=10):
            pass
    except Exception as e:
        print(f"[monitor] TG error: {e}", file=sys.stderr)


def _log_event(event: str, strategy: str, **kw: Any) -> None:
    LOG_JSONL.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": int(time.time()),
        "event": event,
        "strategy": strategy,
        **kw,
    }
    with LOG_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _compute_pf(wins: float, losses: float) -> Optional[float]:
    if losses <= 0:
        return None if wins <= 0 else 99.0
    return round(wins / losses, 3)


def _load_trades_csv() -> List[Dict[str, Any]]:
    """Load all trades from the most recent trades.csv."""
    for candidate in [
        ROOT / "runtime" / "trades.csv",
        ROOT / "trades.csv",
    ]:
        if candidate.exists():
            try:
                with open(candidate, newline="", encoding="utf-8") as f:
                    return list(csv.DictReader(f))
            except Exception:
                pass
    return []


def _load_live_events() -> List[Dict[str, Any]]:
    """Parse live_trade_events.jsonl into a flat list of closed trades."""
    path = ROOT / "runtime" / "live_trade_events.jsonl"
    if not path.exists():
        return []
    trades = []
    buckets: Dict[str, Dict[str, Any]] = {}
    try:
        for raw in path.read_text(errors="ignore").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                evt = json.loads(raw)
            except Exception:
                continue
            event_name = str(evt.get("event") or "").lower()
            if event_name not in {"order_submitted", "entry_filled", "close"}:
                continue
            oid = str(evt.get("entry_order_id") or "|".join([
                str(evt.get("symbol") or ""),
                str(evt.get("strategy") or ""),
                str(evt.get("ts") or ""),
            ]))
            rec = buckets.setdefault(oid, {})
            rec.update({k: v for k, v in evt.items() if v not in (None, "")})
            if event_name == "close":
                rec["exit_ts"] = int(evt.get("ts") or 0)
        for rec in buckets.values():
            if not rec.get("exit_ts"):
                continue
            trades.append({
                "strategy":   str(rec.get("strategy") or ""),
                "exit_ts":    int(rec.get("exit_ts") or 0),
                "pnl":        float(rec.get("pnl") or 0.0),
            })
    except Exception as e:
        print(f"[monitor] live events parse error: {e}", file=sys.stderr)
    return trades


def _get_trades_for_window(days: int) -> List[Dict[str, Any]]:
    """Return trades closed in the last `days` days from any source."""
    cutoff_ms = (time.time() - days * 86400) * 1000
    cutoff_sec = time.time() - days * 86400
    results = []

    # Try CSV first
    for row in _load_trades_csv():
        strategy = str(row.get("strategy") or "").strip()
        if not strategy:
            continue
        # get timestamp
        ts_raw = row.get("exit_ts") or row.get("close_time") or row.get("open_time") or ""
        ts_val = 0.0
        try:
            ts_val = float(ts_raw)
            if ts_val > 1e12:
                ts_val /= 1000.0  # ms → sec
        except (ValueError, TypeError):
            try:
                from datetime import datetime
                ts_val = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
        if ts_val < cutoff_sec:
            continue
        pnl = 0.0
        try:
            pnl = float(row.get("pnl") or row.get("pnl_pct") or 0.0)
        except (ValueError, TypeError):
            pass
        results.append({"strategy": strategy, "exit_ts": ts_val, "pnl": pnl})

    # If no CSV trades, fall back to live events
    if not results:
        for t in _load_live_events():
            if t.get("exit_ts", 0) >= cutoff_sec:
                results.append(t)

    return results


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyse_strategies(days: int = ROLLING_DAYS) -> Dict[str, Any]:
    trades = _get_trades_for_window(days)

    by_strategy: Dict[str, List[float]] = {}
    for t in trades:
        strat = t["strategy"]
        if strat:
            by_strategy.setdefault(strat, []).append(float(t.get("pnl") or 0.0))

    results = {}
    for strat, pnls in by_strategy.items():
        n = len(pnls)
        wins   = sum(p for p in pnls if p > 0)
        losses = abs(sum(p for p in pnls if p < 0))
        win_rate = round(sum(1 for p in pnls if p > 0) / n, 3) if n > 0 else 0.0
        pf = _compute_pf(wins, losses)
        bt_pf = _DEFAULT_BACKTEST_PF.get(strat)

        total_pnl = round(sum(pnls), 4)
        emergency_bleed = (
            n >= EMERGENCY_MIN_TRADES
            and pf is not None
            and pf < EMERGENCY_PF
            and total_pnl <= EMERGENCY_NET_PNL
        )

        status = "ok"
        reason = ""
        if emergency_bleed:
            status = "degraded"
            reason = "emergency_live_bleed"
        elif n < MIN_TRADES:
            status = "insufficient_data"
        elif pf is not None and bt_pf is not None:
            if pf < bt_pf * DEGRADE_THRESHOLD:
                status = "degraded"
                reason = "below_backtest_threshold"
            elif pf < bt_pf * RECOVER_THRESHOLD:
                status = "watch"
                reason = "below_recover_threshold"

        results[strat] = {
            "strategy":         strat,
            "trades_30d":       n,
            "win_rate_30d":     win_rate,
            "live_pf_30d":      pf,
            "backtest_pf_ref":  bt_pf,
            "degrade_threshold": round(bt_pf * DEGRADE_THRESHOLD, 3) if bt_pf else None,
            "recover_threshold": round(bt_pf * RECOVER_THRESHOLD, 3) if bt_pf else None,
            "status":           status,
            "status_reason":    reason,
            "total_pnl_30d":    total_pnl,
        }

    return results


def load_prior_health() -> Dict[str, str]:
    """Return strategy → prior_status from last written health file."""
    if not OUTPUT_HEALTH.exists():
        return {}
    try:
        data = json.loads(OUTPUT_HEALTH.read_text())
        return {k: v.get("status", "ok") for k, v in data.get("strategies", {}).items()}
    except Exception:
        return {}


def write_pause_env(paused: set) -> None:
    lines = [
        "# Auto-generated by live_vs_backtest_monitor.py — do not edit manually",
        f"# Updated: {datetime.now(timezone.utc).isoformat()}",
        "# Strategies paused due to live performance degradation:",
    ]
    for strat in sorted(paused):
        key = _STRATEGY_RISK_KEY.get(strat)
        if key:
            lines.append(f"# {strat} degraded → risk_mult=0.0")
            lines.append(f"{key}=0.0")
    OUTPUT_PAUSE.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(OUTPUT_PAUSE) + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, str(OUTPUT_PAUSE))


def run(dry_run: bool = False) -> None:
    now_utc = datetime.now(timezone.utc).isoformat()
    print(f"[monitor] {now_utc} — running {ROLLING_DAYS}d window, min_trades={MIN_TRADES}")

    results = analyse_strategies(ROLLING_DAYS)
    prior = load_prior_health()

    paused: set = set()
    alerts: list = []

    for strat, info in results.items():
        status = info["status"]
        prev   = prior.get(strat, "ok")

        if status == "degraded":
            paused.add(strat)
            if prev != "degraded":
                # New degradation — alert
                msg = (
                    f"⚠️ <b>Strategy degraded</b>: {strat}\n"
                    f"live PF={info['live_pf_30d']} vs backtest PF={info['backtest_pf_ref']} "
                    f"(threshold={info['degrade_threshold']})\n"
                    f"trades_30d={info['trades_30d']} win_rate={info['win_rate_30d']:.0%}\n"
                    f"reason={info.get('status_reason') or 'degraded'} net={info['total_pnl_30d']:+.4f}\n"
                    f"Action: pausing (risk_mult → 0.0) + queuing re-optimisation"
                )
                alerts.append(msg)
                print(f"[monitor] DEGRADED: {strat} PF={info['live_pf_30d']}")
                if not dry_run:
                    _log_event("strategy_paused", strat,
                               live_pf=info["live_pf_30d"],
                               backtest_pf=info["backtest_pf_ref"],
                               trades_30d=info["trades_30d"])

        elif status in ("ok", "watch") and prev == "degraded":
            # Recovery
            msg = (
                f"✅ <b>Strategy recovered</b>: {strat}\n"
                f"live PF={info['live_pf_30d']} (threshold was {info['degrade_threshold']})\n"
                f"Resuming normal risk allocation."
            )
            alerts.append(msg)
            print(f"[monitor] RECOVERED: {strat} PF={info['live_pf_30d']}")
            if not dry_run:
                _log_event("strategy_recovered", strat,
                           live_pf=info["live_pf_30d"],
                           backtest_pf=info["backtest_pf_ref"])

        label = {"ok": "✅", "watch": "👁️", "degraded": "🔴", "insufficient_data": "⏳"}.get(status, "?")
        pf_str = f"{info['live_pf_30d']:.3f}" if info["live_pf_30d"] is not None else "n/a"
        print(f"  {label} {strat:40s} n={info['trades_30d']:3d} PF={pf_str:6s} "
              f"wr={info['win_rate_30d']:.0%} status={status}")

    health_doc = {
        "updated_at": now_utc,
        "rolling_days": ROLLING_DAYS,
        "total_strategies": len(results),
        "degraded": sorted(paused),
        "strategies": results,
    }

    if not dry_run:
        OUTPUT_HEALTH.write_text(json.dumps(health_doc, indent=2))
        write_pause_env(paused)
        print(f"[monitor] Written → {OUTPUT_HEALTH}")
        print(f"[monitor] Pause env → {OUTPUT_PAUSE} ({len(paused)} paused)")
        for msg in alerts:
            _tg(msg)
    else:
        print("[DRY RUN] Would write:")
        print(json.dumps(health_doc, indent=2))
        if paused:
            print(f"[DRY RUN] Would pause: {sorted(paused)}")

    if not results:
        print("[monitor] No trades found in rolling window — nothing to evaluate")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live vs Backtest Performance Monitor")
    parser.add_argument("--dry-run", action="store_true", help="Print only, no file writes")
    parser.add_argument("--days", type=int, default=ROLLING_DAYS, help="Rolling window days")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
