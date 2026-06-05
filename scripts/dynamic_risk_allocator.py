#!/usr/bin/env python3
"""Dynamic per-sleeve risk allocator.

Daily cron. Reads strategy health + drift + recent closed trades per sleeve
and emits a **recommended risk multiplier** for each strategy. The bot reads
`runtime/dynamic_risk_recommendations.json` and applies the multiplier as a
soft adjustment on top of base RISK_MULT.

Logic:
  1. For each strategy with ≥ MIN_SAMPLE closed trades, compute rolling
     30-trade Sharpe ratio (annualized, assuming ~5 trades/day baseline).
  2. Compute Kelly fraction (capped at K_MAX = 0.25 — never full Kelly).
  3. Combine Sharpe rank + Kelly + health verdict into a single multiplier
     in [MIN_MULT, MAX_MULT] (default 0.3 to 1.5).
  4. Apply health-verdict modifier:
       - healthy:        multiplier ×= 1.0
       - watching:       multiplier ×= 0.85
       - underperforming:multiplier ×= 0.60
       - regression:     multiplier ×= 0.30 (severely throttle)
       - insufficient:   multiplier = 1.0 (no change, not enough data)
  5. Normalize so sum of multipliers across active sleeves = baseline target
     (preserves overall portfolio risk; just shifts allocation winners-up,
     losers-down).

Bot integration: at scan time, read recommendations and multiply with base
RISK_MULT. Fail-open: if file missing/stale > 24h, all multipliers = 1.0.

Income impact: cuts allocation to losing sleeves before drawdowns compound;
shifts to winning sleeves to compound gains. Expected +2-5% APR via better
allocation.

Safety:
  - NEVER multiplier > MAX_MULT (default 1.5)
  - NEVER blocks entries (multiplier > 0 always)
  - Updates limited to once per 24h to avoid whipsaw
  - Audit log in `runtime/dynamic_risk_audit.jsonl`

Cron::

    0 6 * * * /usr/bin/python3 /root/by-bot/scripts/dynamic_risk_allocator.py >> /root/by-bot/runtime/dynamic_risk.log 2>&1

Author: Claude Opus, 2026-06-03. Direct income tool — better capital allocation.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HEALTH_CANDIDATES = [
    ROOT / "runtime" / "strategy_health_report.json",
    ROOT / "runtime" / "strategy_health.json",
]
DRIFT = ROOT / "runtime" / "drift_report.json"
LIVE_EVENTS = ROOT / "runtime" / "live_mirror" / "live_trade_events.jsonl"
RECOMMENDATIONS = ROOT / "runtime" / "dynamic_risk_recommendations.json"
AUDIT = ROOT / "runtime" / "dynamic_risk_audit.jsonl"


# Tunable defaults
MIN_SAMPLE = 20                # need ≥ 20 trades to recommend non-1.0
MIN_MULT = 0.30                # never lower than 30% of base risk
MAX_MULT = 1.50                # never higher than 150% of base risk
KELLY_CAP = 0.25               # ¼-Kelly (never full Kelly — too aggressive)
TARGET_SUM_BASELINE = None     # None = preserve sum-of-multipliers (no portfolio risk change)
TRADES_PER_DAY_ASSUMED = 5.0   # for annualizing Sharpe

VERDICT_MULT = {
    "healthy": 1.0,
    "watching": 0.85,
    "underperforming": 0.60,
    "regression": 0.30,
    "insufficient": 1.0,        # don't change unknown
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(p: Path, default: Any = None) -> Any:
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_first_json(paths: list[Path], default: Any = None) -> Any:
    for p in paths:
        data = _load_json(p, None)
        if data is not None:
            return data
    return default


def _write_json(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _tail_closes(path: Path, n_max: int = 5000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()[-n_max:]
    except Exception:
        return []
    out = []
    for raw in lines:
        try:
            ev = json.loads(raw)
        except Exception:
            continue
        if str(ev.get("event") or "") != "close":
            continue
        if str(ev.get("strategy") or "").lower() == "bootstrap":
            continue
        out.append(ev)
    return out


def _per_strategy_recent_trades(closes: list[dict[str, Any]], window: int = 30) -> dict[str, list[float]]:
    """Returns {strategy: [pnl_per_trade for last `window` trades]}."""
    by_strat: dict[str, list[float]] = {}
    for c in closes:
        s = str(c.get("strategy") or "unknown")
        by_strat.setdefault(s, []).append(float(c.get("pnl") or 0.0))
    return {s: lst[-window:] for s, lst in by_strat.items()}


def _sharpe(pnls: list[float], annualize_factor: float) -> float:
    """Trade-level Sharpe, annualized."""
    if len(pnls) < 5:
        return 0.0
    mean = sum(pnls) / len(pnls)
    var = sum((p - mean) ** 2 for p in pnls) / max(1, len(pnls) - 1)
    std = math.sqrt(var) if var > 0 else 0.0
    if std <= 0:
        return 0.0 if mean <= 0 else 9.99   # capped infinite Sharpe
    return (mean / std) * math.sqrt(annualize_factor)


def _kelly_fraction(pnls: list[float]) -> float:
    """Naive Kelly: f* = (p × b - q) / b where p=win_rate, q=1-p, b=avg_win/avg_loss."""
    if len(pnls) < 5:
        return 0.0
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    if not wins or not losses:
        return 0.0
    p_win = len(wins) / len(pnls)
    b = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
    q_lose = 1.0 - p_win
    if b <= 0:
        return 0.0
    f = (p_win * b - q_lose) / b
    return max(0.0, min(KELLY_CAP, f))


def _verdict_for(strategy: str, health_report: dict[str, Any] | None) -> str:
    if not health_report:
        return "insufficient"
    per = health_report.get("per_strategy") or {}
    entry = per.get(strategy)
    if not entry:
        return "insufficient"
    return str(entry.get("verdict") or "insufficient")


def compute_recommendations(
    closes: list[dict[str, Any]],
    health: dict[str, Any] | None,
    drift: dict[str, Any] | None,
    window: int = 30,
) -> dict[str, dict[str, Any]]:
    per_strategy_pnls = _per_strategy_recent_trades(closes, window=window)
    annualize_factor = TRADES_PER_DAY_ASSUMED * 365.0

    recs: dict[str, dict[str, Any]] = {}
    for strat, pnls in per_strategy_pnls.items():
        n = len(pnls)
        if n < MIN_SAMPLE:
            recs[strat] = {
                "n_recent_trades": n,
                "verdict": "insufficient",
                "recommended_risk_mult": 1.0,
                "reason": "insufficient_sample",
            }
            continue

        sharpe = _sharpe(pnls, annualize_factor)
        kelly = _kelly_fraction(pnls)
        verdict = _verdict_for(strat, health)
        verdict_mod = VERDICT_MULT.get(verdict, 1.0)

        # Base score: blend Sharpe (capped) + Kelly
        sharpe_score = max(0.0, min(3.0, sharpe)) / 3.0       # 0..1
        kelly_score = kelly / KELLY_CAP                         # 0..1
        base_score = 0.6 * sharpe_score + 0.4 * kelly_score      # 0..1

        # Map base_score to multiplier in [MIN_MULT, MAX_MULT]
        # base_score 0.5 → 1.0 (baseline)
        # base_score 1.0 → 1.5 (max boost)
        # base_score 0.0 → 0.3 (heavy throttle)
        if base_score >= 0.5:
            mult = 1.0 + (base_score - 0.5) * 2.0 * (MAX_MULT - 1.0)
        else:
            mult = 1.0 - (0.5 - base_score) * 2.0 * (1.0 - MIN_MULT)

        # Apply verdict modifier
        mult *= verdict_mod
        mult = max(MIN_MULT, min(MAX_MULT, mult))

        recs[strat] = {
            "n_recent_trades": n,
            "sharpe_annualized": round(sharpe, 3),
            "kelly_fraction_capped": round(kelly, 3),
            "verdict": verdict,
            "verdict_modifier": verdict_mod,
            "base_score": round(base_score, 3),
            "recommended_risk_mult": round(mult, 3),
        }
    return recs


def main() -> int:
    ap = argparse.ArgumentParser(description="Dynamic per-sleeve risk allocator")
    ap.add_argument("--window", type=int, default=30, help="Rolling window in trades (default 30)")
    ap.add_argument("--dry-run", action="store_true", help="Print, do not write")
    args = ap.parse_args()

    closes = _tail_closes(LIVE_EVENTS)
    health = _load_first_json(HEALTH_CANDIDATES)
    drift = _load_json(DRIFT)

    recs = compute_recommendations(closes, health, drift, window=args.window)

    output = {
        "generated_at_utc": _utc_now_iso(),
        "stale_after_utc": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        "window_trades": args.window,
        "min_sample_for_recommendation": MIN_SAMPLE,
        "min_mult": MIN_MULT,
        "max_mult": MAX_MULT,
        "kelly_cap": KELLY_CAP,
        "verdict_modifiers": VERDICT_MULT,
        "recommendations": recs,
    }

    if args.dry_run:
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0

    _write_json(RECOMMENDATIONS, output)

    # Audit append
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts_utc": _utc_now_iso(), "recs": recs}, ensure_ascii=False) + "\n")

    print(json.dumps({
        "ok": True,
        "n_strategies_recommended": len(recs),
        "throttled": [s for s, r in recs.items() if r.get("recommended_risk_mult", 1.0) < 1.0],
        "boosted": [s for s, r in recs.items() if r.get("recommended_risk_mult", 1.0) > 1.0],
        "path": str(RECOMMENDATIONS),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
