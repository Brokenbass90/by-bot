#!/usr/bin/env python3
"""Validate pair stat-arb (ETH/BTC etc.) through the Backtest Lab (Opus 2026-06-08).

Simulates the market-neutral pair strategy (strategies/pair_stat_arb_v1) on two
aligned close series and reports honest metrics via backtest.lab + a fee-sensitivity
sweep via backtest.robustness. This tells us whether the "calm arm" has any real
edge BEFORE any capital — net of trading costs on both legs.

Per-trade pair return approximation (market-neutral, equal notional per leg):
    profit ≈ sign(z_entry) * (entry_spread - exit_spread)  - round-trip fees(4 fills)
where spread = log(A) - beta*log(B) (≈ fractional pair return).

Run (Codex/server with data):
    python3 scripts/validate_pair_arb.py --a ETHUSDT --b BTCUSDT --interval 60
Offline self-test runs on synthetic cointegrated data.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.pair_stat_arb_v1 import PairStatArbV1, PairConfig, compute_spread
from backtest.lab import RunResult, report_from_result
from backtest.robustness import fee_sensitivity


def simulate_pair(prices_a: Sequence[float], prices_b: Sequence[float],
                  cfg: PairConfig | None = None, fee_bps: float = 6.0) -> List[Dict[str, float]]:
    cfg = cfg or PairConfig()
    n = min(len(prices_a), len(prices_b))
    a, b = list(prices_a[:n]), list(prices_b[:n])
    eng = PairStatArbV1(cfg)
    trades: List[Dict[str, float]] = []
    in_pos = False
    entry_spread = 0.0
    entry_sign = 0
    fee_cost = 4.0 * fee_bps / 10000.0  # open 2 legs + close 2 legs
    lb = cfg.lookback
    for i in range(lb, n):
        wa, wb = a[: i + 1], b[: i + 1]
        d = eng.diagnostics(wa, wb)
        if not d.get("tradeable"):
            continue
        z = d["z"]
        _, _, spread = compute_spread(wa[-lb:], wb[-lb:])
        cur_spread = spread[-1]
        if not in_pos:
            if abs(z) >= cfg.entry_z and abs(z) < cfg.stop_z:
                in_pos = True
                entry_spread = cur_spread
                entry_sign = 1 if z > 0 else -1
        else:
            exit_now, _ = eng.should_exit(z)
            if exit_now:
                gross = entry_sign * (entry_spread - cur_spread)
                trades.append({"pnl": gross - fee_cost, "return_pct": gross - fee_cost,
                               "fees": fee_cost})
                in_pos = False
    return trades


def _gen_cointegrated(n=400, beta=1.0, seed=0):
    import random
    rng = random.Random(seed)
    logb = [math.log(30000.0)]
    for _ in range(n - 1):
        logb.append(logb[-1] + rng.gauss(0, 0.01))
    s = [0.0]
    for _ in range(n - 1):
        s.append(0.8 * s[-1] + rng.gauss(0, 0.01))
    loga = [beta * lb + sp + math.log(0.05) for lb, sp in zip(logb, s)]
    return [math.exp(x) for x in loga], [math.exp(x) for x in logb]


def run_report(a, b, cfg=None, fee_bps=6.0, name="pair") -> Dict[str, Any]:
    trades = simulate_pair(a, b, cfg, fee_bps)
    rep = report_from_result(RunResult(trades=trades, meta={"name": name}))
    rets = [t["return_pct"] for t in trades]
    rep["fee_sensitivity"] = fee_sensitivity(rets, fee_bps_list=(6.0, 8.0, 10.0)) if rets else {"verdict": "no_trades"}
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default=""); ap.add_argument("--b", default="")
    ap.add_argument("--interval", default="60")
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--lookback", type=int, default=168)
    args = ap.parse_args()
    cfg = PairConfig(lookback=args.lookback)
    if not args.a or not args.b:
        print("No --a/--b given → synthetic self-test (cointegrated pair):")
        a, b = _gen_cointegrated()
        import json
        print(json.dumps(run_report(a, b, cfg, args.fee_bps, "synthetic"), indent=2))
        return 0
    # real data: load aligned closes from cache (Codex/server)
    import glob, csv, json, os
    def load(sym):
        rows = {}
        for f in glob.glob(f"data_cache/{sym}_{args.interval}_*.json"):
            try:
                for r in json.load(open(f)):
                    rows[int(r["ts"])] = float(r["c"])
            except Exception:
                pass
        for f in glob.glob(f"data_cache/equities_1h/{sym}_*.csv") + glob.glob(f"data/equities_daily/{sym}*.csv"):
            try:
                for r in csv.DictReader(open(f)):
                    rows[int(r["ts"])] = float(r["c"])
            except Exception:
                pass
        return rows
    ra, rb = load(args.a), load(args.b)
    common = sorted(set(ra) & set(rb))
    a = [ra[t] for t in common]; b = [rb[t] for t in common]
    print(f"aligned bars: {len(a)}")
    if len(a) < cfg.lookback + 10:
        print("not enough aligned data (need cache); run on server with full data"); return 1
    import json
    print(json.dumps(run_report(a, b, cfg, args.fee_bps, f"{args.a}/{args.b}"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
