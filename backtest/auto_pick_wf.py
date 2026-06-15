"""Multi-strategy walk-forward UNDER automatic coin selection.

This is the realistic test the owner asked for: don't hand-pick SOL — let the
live scorer (scripts/strategy_scorer) choose each strategy's coins, then run the
multi-window WF (ladder exit + fees) on those auto-picked coins, for several
strategies at once. The output is a matrix of strategy x coin pockets that pass
the anti-overfit gate -> candidates for a tiny shadow/canary.

IMPORTANT: the auto-picked coins are mostly NOT in the local cache, so locally
this prints "no data" for most — proving the run belongs on the SERVER, where
the live feed has every coin. Codex runs it there; the tooling is identical.

Run (server, after refreshing reports/STRATEGY_COIN_PICKS_latest.json):
    PYTHONPATH=. python backtest/auto_pick_wf.py
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from backtest.crypto_multiwindow_wf import run as mw_run

ROOT = Path(__file__).resolve().parents[1]

# strategy -> (module path, class name, tf override env prefix)
STRATS = {
    "ASB1": ("strategies.alt_support_bounce_v1", "AltSupportBounceV1Strategy", "ASB1"),
    "ARF1": ("strategies.alt_resistance_fade_v1", "AltResistanceFadeV1Strategy", "ARF1"),
    "BREAKDOWN": ("strategies.alt_inplay_breakdown_v1", "AltInplayBreakdownV1Strategy", "BREAKDOWN"),
}


def _factory(modpath, clsname):
    import importlib
    cls = getattr(importlib.import_module(modpath), clsname)
    return lambda: cls()


def _majority_positive(pos: int, n: int) -> bool:
    return n >= 2 and pos > n / 2.0


def main(top_k=4, fee_bps=10.0, signal_tf="60", regime_tf="240", windows=4, output_json: str = ""):
    picks_path = ROOT / "reports" / "STRATEGY_COIN_PICKS_latest.json"
    if not picks_path.exists():
        print("run scripts/strategy_coin_picks.py first")
        return {}
    picks = json.loads(picks_path.read_text(encoding="utf-8"))
    print(
        "=== multi-strategy WF under AUTO coin selection "
        f"(top {top_k}, {fee_bps}bps, signal_tf={signal_tf}, regime_tf={regime_tf}) ==="
    )
    summary = {}
    matrix = {}
    for strat, (modpath, clsname, pref) in STRATS.items():
        if strat not in picks:
            continue
        os.environ[f"{pref}_REGIME_TF"] = str(regime_tf)
        os.environ[f"{pref}_SIGNAL_TF"] = str(signal_tf)
        factory = _factory(modpath, clsname)
        coins = [s for s, _ in picks[strat][:top_k]]
        print(f"\n## {strat} — auto-picked: {coins}")
        matrix[strat] = {}
        for coin in coins:
            result = mw_run(
                factory,
                coin,
                signal_tf=str(signal_tf),
                regime_tf=str(regime_tf),
                k=int(windows),
                fee_bps=float(fee_bps),
                return_details=True,
            )
            edges = result.get("edges") or []
            matrix[strat][coin] = result
            if edges:
                pos = sum(1 for e in edges if e > 0)
                summary.setdefault(strat, []).append((coin, pos, len(edges)))
    print("\n=== PASS candidates (majority windows positive) ===")
    any_pass = False
    pass_candidates = []
    for strat, rows in summary.items():
        for coin, pos, n in rows:
            if _majority_positive(pos, n):
                print(f"  {strat} / {coin}: {pos}/{n} windows positive -> canary candidate")
                any_pass = True
                pass_candidates.append({"strategy": strat, "symbol": coin, "positive_windows": pos, "windows_with_trades": n})
    if not any_pass:
        print("  none passed the majority-positive gate")
    out = {
        "top_k": int(top_k),
        "fee_bps": float(fee_bps),
        "signal_tf": str(signal_tf),
        "regime_tf": str(regime_tf),
        "windows": int(windows),
        "pass_candidates": pass_candidates,
        "matrix": matrix,
    }
    path = Path(output_json) if output_json else ROOT / "reports" / "AUTO_PICK_WF_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {path}")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-strategy WF under automatic coin selection")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--fee-bps", type=float, default=10.0)
    parser.add_argument("--signal-tf", default="60")
    parser.add_argument("--regime-tf", default="240")
    parser.add_argument("--windows", type=int, default=4)
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()
    main(
        top_k=args.top_k,
        fee_bps=args.fee_bps,
        signal_tf=args.signal_tf,
        regime_tf=args.regime_tf,
        windows=args.windows,
        output_json=args.output_json,
    )
