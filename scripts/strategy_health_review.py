#!/usr/bin/env python3
"""Strategy health review — rolling-window live vs backtest expectation.

Daily cron. For each strategy that has produced ≥ `MIN_SAMPLE` live closed
trades, compares live metrics over rolling windows against the strategy's
backtest expectation. Generates a structured health verdict per sleeve.

This is **complementary** to `drift_detector.py`:
  - drift_detector compares RECENT vs PRIOR LIVE (catches degradation)
  - strategy_health_review compares LIVE vs BACKTEST EXPECTED (catches
    strategies that never worked in live conditions, even from day 1)

Verdicts:
  - "insufficient" — sample too small to conclude (default < 10 trades)
  - "healthy"      — live within backtest expectation tolerance
  - "watching"     — live shows mild divergence, monitor
  - "underperforming" — significant divergence sustained over 20+ trades
  - "regression"   — severe divergence over 30+ trades, consider pause

Expectations are loaded from `runtime/strategy_health_expectations.json`
(auto-bootstrapped from known baselines if missing):

    {
      "alt_inplay_breakdown_v1": {
          "expected_winrate_pct": 59.4,
          "expected_pf": 1.591,
          "expected_avg_pnl_pct": null,  // null = use winrate+pf to derive
          "source": "crypto_income_static_v1 baseline"
      },
      ...
    }

Output:
  - `runtime/strategy_health_report.json` (structured)
  - Optional Telegram alert (if any sleeve verdict >= "underperforming")
  - Auto-suggestion: demote sleeve in strategy_pipeline.json with `--reason`

Bot integration suggestion: at startup, bot reads
`runtime/strategy_health_report.json` and reduces risk_mult for any sleeve
flagged as "underperforming" or "regression" by 30% / 50% respectively.
That is a soft safety, NOT a hard disable.

Cron suggestion: 1 per day, e.g.

    45 7 * * * /usr/bin/python3 /root/by-bot/scripts/strategy_health_review.py >> /root/by-bot/runtime/strategy_health.log 2>&1

Author: Claude Opus, 2026-06-03. Live-vs-backtest divergence guardian.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
LIVE_EVENT_CANDIDATES = (
    ROOT / "runtime" / "live_trade_events.jsonl",
    ROOT / "runtime" / "live_mirror" / "live_trade_events.jsonl",
)
EXPECTATIONS = ROOT / "runtime" / "strategy_health_expectations.json"
REPORT_OUT = ROOT / "runtime" / "strategy_health_report.json"
PIPELINE_FILE = ROOT / "runtime" / "strategy_pipeline.json"

_SSL = ssl.create_default_context()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(p: Path, default: Any = None) -> Any:
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


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


# ---------------------------------------------------------------------------
# Default expectations (baseline crypto_income_static_v1 derived)
# ---------------------------------------------------------------------------

# IMPORTANT: keys are the EXACT strategy field as logged in
# live_trade_events.jsonl (NOT the source-file module name). Examples:
#   - "alt_inplay_breakdown_v1" (matches module)
#   - "att1_trendline_touch"    (NOT "alt_trendline_touch_v1")
#   - "range"                   (NOT "alt_range_scalp_v1")
DEFAULT_EXPECTATIONS = {
    "alt_inplay_breakdown_v1": {
        "expected_winrate_pct": 59.4,
        "expected_pf": 1.591,
        "expected_avg_pnl_pct": None,
        "source": "crypto_income_static_v1 baseline 365d",
    },
    "att1_trendline_touch": {
        "expected_winrate_pct": 59.0,
        "expected_pf": 1.55,
        "expected_avg_pnl_pct": None,
        "source": "crypto_income_static_v1 baseline 365d (ATT1 attribution)",
    },
    "range": {
        "expected_winrate_pct": 55.0,
        "expected_pf": 1.30,
        "expected_avg_pnl_pct": None,
        "source": "range/alt_range_scalp_v1 historical (estimate)",
    },
    "alt_resistance_fade_v1": {
        "expected_winrate_pct": 60.0,
        "expected_pf": 1.65,
        "expected_avg_pnl_pct": None,
        "source": "ARF1 r002 winner replay full-package",
    },
    "btc_eth_midterm_pullback": {
        "expected_winrate_pct": 55.0,
        "expected_pf": 1.45,
        "expected_avg_pnl_pct": None,
        "source": "MTPB baseline (low-frequency)",
    },
    "alt_sloped_channel_v1": {
        "expected_winrate_pct": 57.0,
        "expected_pf": 1.40,
        "expected_avg_pnl_pct": None,
        "source": "ASC1 historical (estimate)",
    },
    "alt_bear_regime_continuation_v1": {
        "expected_winrate_pct": 67.7,
        "expected_pf": 4.8,
        "expected_avg_pnl_pct": None,
        "source": "BRC1 r005 fast 90d (extreme PF — small sample)",
    },
    "pump_fade_smart_v1": {
        "expected_winrate_pct": 55.0,
        "expected_pf": 1.30,
        "expected_avg_pnl_pct": None,
        "source": "PFS1 design target (no backtest yet)",
    },
    "grid_smart_v1": {
        "expected_winrate_pct": 60.0,
        "expected_pf": 1.20,
        "expected_avg_pnl_pct": None,
        "source": "GS1 design target (no backtest yet)",
    },
}


# ---------------------------------------------------------------------------
# Verdict thresholds
# ---------------------------------------------------------------------------

# (winrate_delta_pp_threshold, pf_ratio_threshold, min_trades_threshold)
THRESHOLDS = {
    "watching":         (8.0, 0.85, 10),   # 8pp below OR pf < 85% of expected
    "underperforming":  (15.0, 0.65, 20),  # 15pp below AND/OR pf < 65%
    "regression":       (25.0, 0.40, 30),  # severe, sustained
}


def _classify(live_wr: float, live_pf: float,
              expected_wr: float, expected_pf: float, n_trades: int) -> dict[str, Any]:
    """Returns {verdict, flags}."""
    flags: list[str] = []

    if n_trades < 10:
        return {"verdict": "insufficient", "flags": ["sample_below_10"], "details": {}}

    wr_delta_pp = expected_wr - live_wr
    pf_ratio = (live_pf / expected_pf) if expected_pf > 0 else 1.0

    details = {
        "live_wr_pct": round(live_wr, 2),
        "expected_wr_pct": round(expected_wr, 2),
        "wr_delta_pp": round(wr_delta_pp, 2),
        "live_pf": round(live_pf, 3),
        "expected_pf": round(expected_pf, 3),
        "pf_ratio": round(pf_ratio, 3),
    }

    # Check regression (worst) first
    th = THRESHOLDS["regression"]
    if n_trades >= th[2] and (wr_delta_pp >= th[0] or pf_ratio < th[1]):
        flags.append("regression_severe")
        return {"verdict": "regression", "flags": flags, "details": details}

    th = THRESHOLDS["underperforming"]
    if n_trades >= th[2] and (wr_delta_pp >= th[0] or pf_ratio < th[1]):
        flags.append("underperforming")
        return {"verdict": "underperforming", "flags": flags, "details": details}

    th = THRESHOLDS["watching"]
    if n_trades >= th[2] and (wr_delta_pp >= th[0] or pf_ratio < th[1]):
        flags.append("mild_divergence")
        return {"verdict": "watching", "flags": flags, "details": details}

    return {"verdict": "healthy", "flags": [], "details": details}


def _stats_for(closes: list[dict[str, Any]]) -> dict[str, float]:
    if not closes:
        return {"n": 0, "winrate_pct": 0.0, "profit_factor": 0.0, "avg_pnl": 0.0}
    wins = sum(1 for c in closes if float(c.get("pnl") or 0.0) > 0)
    gross_w = sum(float(c.get("pnl") or 0.0) for c in closes if float(c.get("pnl") or 0.0) > 0)
    gross_l = sum(abs(float(c.get("pnl") or 0.0)) for c in closes if float(c.get("pnl") or 0.0) < 0)
    n = len(closes)
    return {
        "n": n,
        "winrate_pct": (wins / n) * 100.0,
        "profit_factor": (gross_w / gross_l) if gross_l > 0 else (99.0 if gross_w > 0 else 0.0),
        "avg_pnl": sum(float(c.get("pnl") or 0.0) for c in closes) / n,
    }


def _live_events_path() -> Path | None:
    """Prefer the live bot journal and fall back to a synced mirror."""
    return next((path for path in LIVE_EVENT_CANDIDATES if path.exists()), None)


def _tail_closes(n_max: int = 10000) -> list[dict[str, Any]]:
    live_events = _live_events_path()
    if live_events is None:
        return []
    try:
        with live_events.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()[-n_max:]
    except Exception:
        return []
    closes = []
    for raw in lines:
        try:
            ev = json.loads(raw)
        except Exception:
            continue
        if str(ev.get("event") or "") != "close":
            continue
        # Skip bootstrap-labelled positions (not algo)
        if str(ev.get("strategy") or "").lower() == "bootstrap":
            continue
        closes.append(ev)
    closes.sort(key=lambda c: int(c.get("ts") or 0))
    return closes


def _tg_send(text: str) -> None:
    token = (os.getenv("TG_BOT_TOKEN") or os.getenv("TG_TOKEN") or "").strip()
    chat = (os.getenv("TG_CHAT_ID") or os.getenv("TG_CHAT") or "").strip()
    if not (token and chat):
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000],
                                   "disable_web_page_preview": "true"}).encode()
    req = request.Request(url, data=body, method="POST",
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        request.urlopen(req, context=_SSL, timeout=15).read()
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Strategy health review")
    ap.add_argument("--window-trades", type=int, default=50,
                    help="Take last N closed trades per strategy (default 50)")
    ap.add_argument("--all-history", action="store_true",
                    help="Use ALL history per strategy instead of windowed")
    ap.add_argument("--notify-tg", action="store_true",
                    help="Send TG alert if any sleeve >= underperforming")
    ap.add_argument("--auto-demote", action="store_true",
                    help="Auto-demote sleeves with verdict='regression' in pipeline (not bot)")
    args = ap.parse_args()

    _load_env_file(ROOT / ".env")

    # Bootstrap expectations file if missing
    expectations = _load_json(EXPECTATIONS)
    if not expectations:
        expectations = DEFAULT_EXPECTATIONS
        _write_json(EXPECTATIONS, expectations)

    closes = _tail_closes(10000)
    live_events = _live_events_path()
    if not closes:
        report = {
            "generated_at_utc": _utc_now_iso(),
            "note": "no_live_closes",
            "live_events_source": str(live_events) if live_events else None,
            "per_strategy": {},
        }
        _write_json(REPORT_OUT, report)
        print(json.dumps({"verdict_summary": "no_data"}, ensure_ascii=False))
        return 0

    # Group by strategy
    by_strat: dict[str, list[dict[str, Any]]] = {}
    for c in closes:
        s = str(c.get("strategy") or "unknown")
        by_strat.setdefault(s, []).append(c)

    per_strategy: dict[str, dict[str, Any]] = {}
    for strat, lst in by_strat.items():
        if args.all_history:
            window = lst
        else:
            window = lst[-args.window_trades:]
        live = _stats_for(window)

        exp = expectations.get(strat) or {}
        exp_wr = float(exp.get("expected_winrate_pct") or 50.0)
        exp_pf = float(exp.get("expected_pf") or 1.0)

        cls = _classify(live["winrate_pct"], live["profit_factor"], exp_wr, exp_pf, live["n"])

        per_strategy[strat] = {
            "strategy": strat,
            "trades_window": len(window),
            "trades_total": len(lst),
            "live": live,
            "expected": {"winrate_pct": exp_wr, "profit_factor": exp_pf, "source": exp.get("source", "default")},
            "verdict": cls["verdict"],
            "flags": cls["flags"],
            "details": cls["details"],
        }

    # Overall verdict
    order = {"insufficient": 0, "healthy": 1, "watching": 2, "underperforming": 3, "regression": 4}
    worst = max((order.get(v["verdict"], 0) for v in per_strategy.values()), default=0)
    verdict_label = next((k for k, v in order.items() if v == worst), "healthy")

    report = {
        "generated_at_utc": _utc_now_iso(),
        "window_trades": args.window_trades if not args.all_history else "all_history",
        "live_events_source": str(live_events) if live_events else None,
        "thresholds": THRESHOLDS,
        "overall_verdict": verdict_label,
        "per_strategy": per_strategy,
    }
    _write_json(REPORT_OUT, report)

    # Auto-demote in pipeline (NOT in bot)
    demoted: list[str] = []
    if args.auto_demote:
        pipeline = _load_json(PIPELINE_FILE) or {}
        strategies = pipeline.get("strategies") or {}
        for strat, v in per_strategy.items():
            if v["verdict"] != "regression":
                continue
            # Find pipeline entry by module match
            for fam, entry in strategies.items():
                if entry.get("module") == strat:
                    cur_stage = entry.get("stage", "inventory")
                    # Demote one step (but never to "inventory" via this auto)
                    stages_order = ["inventory", "audit_passed", "unit_smoke", "backtest_seeded",
                                    "sweep_complete", "package_replay_passed", "shadow_30d",
                                    "live_canary", "live_full"]
                    if cur_stage in stages_order:
                        idx = stages_order.index(cur_stage)
                        if idx > 4:  # Only demote from shadow/live levels
                            entry["stage"] = stages_order[idx - 1]
                            entry["auto_demoted_at_utc"] = _utc_now_iso()
                            entry["auto_demote_reason"] = f"strategy_health: regression ({v['details']})"
                            demoted.append(fam)
        if demoted:
            _write_json(PIPELINE_FILE, pipeline)

    # Telegram alert
    if args.notify_tg and verdict_label in {"underperforming", "regression"}:
        bullets = []
        for strat, v in per_strategy.items():
            if v["verdict"] not in {"underperforming", "regression"}:
                continue
            d = v["details"]
            bullets.append(
                f"  • {strat} [{v['verdict']}] n={v['trades_window']}: "
                f"WR {d.get('live_wr_pct','?')}% vs {d.get('expected_wr_pct','?')}%, "
                f"PF {d.get('live_pf','?')} vs {d.get('expected_pf','?')}"
            )
        msg = (f"🩺 Strategy health: overall = *{verdict_label}*\n"
               + "\n".join(bullets)
               + (f"\n\nAuto-demoted: {', '.join(demoted)}" if demoted else ""))
        _tg_send(msg)

    print(json.dumps({
        "overall_verdict": verdict_label,
        "n_strategies": len(per_strategy),
        "demoted": demoted,
        "report_path": str(REPORT_OUT),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
