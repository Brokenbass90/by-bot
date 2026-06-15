"""Walk-forward-style parameter robustness for alpaca_adaptive_v1.

This is 'tuning done right': we DON'T pick the single best backtest number
(that's curve-fitting / overfit — what destroyed the original numbers). We
sweep each knob and look for a ROBUST PLATEAU (neighbouring values agree) vs a
fragile SPIKE (one lucky value). A plateau = real; a spike = overfit.

Additive / standalone. Local cache is mostly bull (~2023-26), so absolute
numbers are optimistic — the value is the SHAPE (plateau vs spike) and the
p-hacking check (fraction of configs that are profitable).
"""
from __future__ import annotations

from backtest.alpaca_adaptive_backtest import run
from strategies.alpaca_adaptive_v1 import AdaptiveConfig


def sweep(label, configs):
    print(f"\n--- {label} ---")
    rows = []
    for desc, cfg in configs:
        m = run(use_gate=True, cfg=cfg)
        rows.append((desc, m["cagr_pct"], m["max_dd_pct"]))
        print(f"  {desc:<22} CAGR={m['cagr_pct']:+5.1f}%  maxDD={m['max_dd_pct']:4.1f}%")
    cagrs = [r[1] for r in rows]
    prof = sum(1 for c in cagrs if c > 0)
    spread = max(cagrs) - min(cagrs)
    verdict = "PLATEAU (robust)" if spread < 8 else "SPIKY (fragile/overfit risk)"
    print(f"  -> profitable {prof}/{len(rows)} | spread {spread:.1f}pp -> {verdict}")
    return rows


if __name__ == "__main__":
    print("=== alpaca_adaptive_v1 parameter robustness (plateau = good, spike = overfit) ===")

    sweep("regime gate SMA length", [
        (f"regime_sma={n}", AdaptiveConfig(regime_index_sma=n)) for n in (100, 150, 200, 250)
    ])
    sweep("number of positions", [
        (f"top_n={t},max_pos={p}", AdaptiveConfig(top_n=t, max_positions=p))
        for (t, p) in ((4, 3), (5, 4), (7, 5), (10, 8))
    ])
    sweep("risk-parity target_vol", [
        (f"target_vol={v}", AdaptiveConfig(target_vol=v)) for v in (0.01, 0.015, 0.02, 0.03)
    ])
    sweep("min momentum filter", [
        (f"min_entry_mom={m}", AdaptiveConfig(min_entry_mom=m)) for m in (-0.05, 0.0, 0.05, 0.10)
    ])
    print("\nRule: prefer the centre of a PLATEAU, never the tip of a SPIKE.")
