# Codex Task — inplay_breakout Retune (2026-04-19)

## Context

`inplay_breakout` is **disabled in ALL current regime overlays** (`ENABLE_BREAKOUT_TRADING=0`
in bull_trend, bear_chop, bear_trend). The comment in bull_trend.env says "OFF until retune".

The previous 50-run sweep (`inplay_breakout_retest_focus_v1`) produced **invalid results** —
all 50 runs returned identical cached trades (21 trades PF=0.520 for odd runs, 17 trades
PF=0.512 for even runs) regardless of what parameters were varied. This happened because
`BACKTEST_CACHE_ONLY=1` means the cache is hit before any env vars take effect — the cache
key doesn't include strategy parameters.

**Only valid data points:**
- 360d backtest ending 2026-02-24 (via sweep): 21 trades, PF=0.520 — **losing**
- 2025 standalone: 3 trades, PF=2.005 — promising but too few
- 2022–2024: 0 trades (candle cache missing for those years)
- 2026 YTD: 0 trades (EMA regime filter blocks all longs in bear market)

**Core problem:** `regime_mode` is hardcoded to `'ema'` (4H EMA20 > EMA50 required for longs).
In bear/chop market (most of 2025), this blocks all signals. Need to characterize what the
strategy produces with and without the regime filter, then decide if it has edge.

Branch: `codex/dynamic-symbol-filters`

---

## Step 1 — Raw signal quality (no regime filter, no cache_only)

First understand what the engine actually does, unconstrained:

```bash
cd /root/by-bot
git pull origin codex/dynamic-symbol-filters
source .venv/bin/activate

BREAKOUT_REGIME_MODE=any \
BREAKOUT_ALLOW_LONGS=1 \
BREAKOUT_ALLOW_SHORTS=0 \
python3 backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOGEUSDT \
  --strategies inplay_breakout \
  --days 360 \
  --end 2026-04-01 \
  --tag breakout_regime_off_360d \
  --starting_equity 100 --risk_pct 0.01 --leverage 1 \
  --fee_bps 6 --slippage_bps 2 \
  2>&1 | tee /tmp/breakout_regime_off.log
```

Print: trades, PF, WR, max_dd.

**If 0 trades: stop here.** The engine itself has a signal generation problem.
**If trades ≥ 20:** proceed to Step 2.

---

## Step 2 — With EMA regime filter (realistic)

```bash
BREAKOUT_REGIME_MODE=ema \
BREAKOUT_ALLOW_LONGS=1 \
BREAKOUT_ALLOW_SHORTS=0 \
python3 backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOGEUSDT \
  --strategies inplay_breakout \
  --days 360 \
  --end 2026-04-01 \
  --tag breakout_ema_regime_360d \
  --starting_equity 100 --risk_pct 0.01 --leverage 1 \
  --fee_bps 6 --slippage_bps 2
```

Compare trades/PF vs Step 1. The delta shows how much the EMA filter costs in frequency.

---

## Step 3 — 5-year historical view (no cache_only, will download data)

```bash
for end_date in 2023-12-31 2024-12-31 2025-12-31; do
  BREAKOUT_REGIME_MODE=any \
  BREAKOUT_ALLOW_LONGS=1 \
  BREAKOUT_ALLOW_SHORTS=0 \
  python3 backtest/run_portfolio.py \
    --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
    --strategies inplay_breakout \
    --days 365 \
    --end $end_date \
    --tag breakout_regime_off_${end_date:0:4} \
    --starting_equity 100 --risk_pct 0.01 --leverage 1 \
    --fee_bps 6 --slippage_bps 2
done
```

Print trades + PF for each year. This reveals if the strategy has any historical edge.

---

## Step 4 — Parameter sweep with corrected SL/TP scaling (NO cache_only)

**Code fix committed:** Two new parameters added to `InPlayBreakoutStrategy`:
- `BREAKOUT_SL_HTF_MULT` — when > 0, SL uses 4H ATR instead of 5m ATR (fixes stop-out bug)
- `BREAKOUT_MAX_DIST_HTF_MULT` — when > 0, max_dist uses 4H ATR (fixes "too far" filter)

**CRITICAL: Do NOT use BACKTEST_CACHE_ONLY=1 — that invalidated all 50 previous runs.**
The cache key doesn't include env vars, so all combos returned the same cached result.

```bash
python3 << 'PYEOF'
import subprocess, itertools, csv, os, glob

params = {
    "BREAKOUT_REGIME_MODE":      ["any", "ema"],
    "BREAKOUT_SL_HTF_MULT":      ["0.8", "1.0", "1.5"],   # 4H ATR based SL (NEW FIX)
    "BREAKOUT_MAX_DIST_HTF_MULT": ["1.0", "1.5", "2.0"],  # 4H ATR based max_dist (NEW FIX)
    "BREAKOUT_RR":               ["2.5", "3.0", "4.0"],   # much larger TP vs 4H SL
    "BREAKOUT_IMPULSE_ATR_MULT": ["0.8", "1.0", "1.3"],
}
base_env = {
    "BREAKOUT_ALLOW_LONGS": "1",
    "BREAKOUT_ALLOW_SHORTS": "0",
    "BREAKOUT_RETEST_TOUCH_ATR": "0.30",
    # NO BACKTEST_CACHE_ONLY
}

keys = list(params.keys())
results = []
for combo in itertools.product(*params.values()):
    env = {**os.environ, **base_env, **dict(zip(keys, combo))}
    tag = "brk2_" + "_".join(v.replace(".","").replace("-","") for v in combo)[:35]
    cmd = [
        ".venv/bin/python", "backtest/run_portfolio.py",
        "--symbols", "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT",
        "--strategies", "inplay_breakout",
        "--days", "365", "--end", "2025-12-31",
        "--tag", tag,
        "--starting_equity", "100", "--risk_pct", "0.01",
        "--leverage", "1", "--fee_bps", "6", "--slippage_bps", "2",
    ]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd="/root/by-bot")
    runs = sorted(glob.glob(f"/root/by-bot/backtest_runs/portfolio_*_{tag}"))
    if runs:
        sf = runs[-1] + "/summary.csv"
        if os.path.exists(sf):
            row = list(csv.DictReader(open(sf)))[0]
            t = int(row.get("trades", 0))
            pf = float(row.get("profit_factor", 0))
            if t >= 10 and pf >= 1.20:
                results.append({
                    "params": dict(zip(keys, combo)),
                    "trades": t, "pf": pf,
                    "wr": float(row.get("winrate", 0)),
                    "dd": float(row.get("max_drawdown", 0)),
                    "pnl": float(row.get("net_pnl", 0)),
                })

results.sort(key=lambda x: x["pf"] * min(1, x["trades"]/20), reverse=True)
print(f"Qualifying (PF>=1.20, trades>=10): {len(results)}")
for r in results[:15]:
    p = r["params"]
    print(f"  regime={p['BREAKOUT_REGIME_MODE']} sl_htf={p['BREAKOUT_SL_HTF_MULT']} "
          f"dist_htf={p['BREAKOUT_MAX_DIST_HTF_MULT']} rr={p['BREAKOUT_RR']} "
          f"imp={p['BREAKOUT_IMPULSE_ATR_MULT']} -> t={r['trades']} PF={r['pf']:.3f} "
          f"wr={r['wr']*100:.0f}% dd={r['dd']:.1f}% pnl={r['pnl']:.1f}%")
PYEOF
```

---

## Step 5 — WF-22 if PF ≥ 1.25 found

If Step 4 yields a config with PF ≥ 1.25 and ≥ 30 trades/year:

```bash
BREAKOUT_REGIME_MODE=<best> \
BREAKOUT_RETEST_TOUCH_ATR=<best> \
BREAKOUT_MAX_DIST_ATR=<best> \
BREAKOUT_IMPULSE_ATR_MULT=<best> \
BREAKOUT_RR=<best> \
BREAKOUT_ALLOW_LONGS=1 \
python3 scripts/run_crypto_core_walkforward.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
  --strategies inplay_breakout \
  --end 2026-04-18 \
  --total_days 330 --window_days 15 --step_days 15 \
  --min_pf 1.20 --min_net 0.0 --max_dd 25.0 \
  --tag breakout_wf22_best \
  2>&1 | tee /tmp/breakout_wf22.log

WF_DIR=$(ls -1dt backtest_runs/walkforward_*_breakout_wf22_best | head -1)
cat "$WF_DIR/walkforward_report.md"
```

---

## Expected outcomes

| Result | Action |
|--------|--------|
| Step 1: 0 trades with regime=any | Strategy engine is broken — needs signal redesign |
| Step 1: trades≥20 but PF<1.0 all years | No historical edge — archive strategy |
| Some years PF≥1.2 | Run sweep (Step 4), look for consistent configs |
| Step 4 finds PF≥1.25, trades≥30/y | WF-22 gate (Step 5) |
| WF-22 AvgPF≥1.20 | Re-enable in bull_trend: `ENABLE_BREAKOUT_TRADING=1`, update regime overlay |

---

## Notes

- **DO NOT use `BACKTEST_CACHE_ONLY=1` in parameter sweeps** — this caused all 50 previous
  sweep runs to return identical cached results (same 21 trades PF=0.520 for every combo)
- The cache collision happened because the cache key uses (symbol, days, end_date) only —
  not the env vars controlling strategy behavior
- Strategy prefix: `BREAKOUT_*` env vars
- The `regime_mode='ema'` filter (4H EMA20 > EMA50) is hardcoded to fall back to 'ema' —
  use `BREAKOUT_REGIME_MODE=any` to test without it
- Allow shorts: `BREAKOUT_ALLOW_SHORTS=1` to test short-side (was previously disabled)
- If signal redesign needed: the core issue is low impulse quality — consider adding
  `BREAKOUT_MIN_VOL_MULT` requirement (volume spike on breakout bar) and tighter
  `BREAKOUT_IMPULSE_BODY_MIN_FRAC` to filter fake breakouts
