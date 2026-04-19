# Codex 3-Day Queue (2026-04-19 → 2026-04-22)

Branch: `codex/dynamic-symbol-filters` — pull before each task.

Run tasks in order. Each task has a gate: if it fails, move on but log the failure.

---

## DAY 1 — Re-enable breakdown + fix inplay_breakout

### Task 1.1 — Breakdown v1 WF-22 with optimal params

Sweep found best params: LOOKBACK_H=36, MIN_BREAK_ATR=0.15, SL_ATR=1.4, RR=2.0.
Recent 90d: PF=4.299 WR=74% DD=2%. Recent 180d: PF=2.113 t=56. Run WF-22 to confirm.

```bash
cd /root/by-bot
git pull origin codex/dynamic-symbol-filters
source .venv/bin/activate

BREAKDOWN_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT \
BREAKDOWN_LOOKBACK_H=36 \
BREAKDOWN_MIN_BREAK_ATR=0.15 \
BREAKDOWN_RSI_MAX=50 \
BREAKDOWN_SL_ATR=1.4 \
BREAKDOWN_RR=2.0 \
BREAKDOWN_ALLOW_SHORTS=1 \
BREAKDOWN_ALLOW_LONGS=0 \
python3 scripts/run_crypto_core_walkforward.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT \
  --strategies alt_inplay_breakdown_v1 \
  --end 2026-04-18 \
  --total_days 330 --window_days 15 --step_days 15 \
  --min_pf 1.20 --min_net 0.0 --max_dd 25.0 \
  --tag breakdown_v1_wf22_best \
  2>&1 | tee /tmp/breakdown_v1_wf22.log

WF_DIR=$(ls -1dt backtest_runs/walkforward_*_breakdown_v1_wf22_best | head -1)
cat "$WF_DIR/walkforward_report.md"
```

**Gate:** If AvgPF ≥ 1.20 across ≥ 16/22 windows → update `configs/regime_overlay_bear_chop.env`
and `configs/regime_overlay_bear_trend.env` to enable:
```
ENABLE_BREAKDOWN_TRADING=1
BREAKDOWN_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT
BREAKDOWN_LOOKBACK_H=36
BREAKDOWN_MIN_BREAK_ATR=0.15
BREAKDOWN_RSI_MAX=50
BREAKDOWN_SL_ATR=1.4
BREAKDOWN_RR=2.0
BREAKDOWN_ALLOW_SHORTS=1
BREAKDOWN_ALLOW_LONGS=0
```
Also add to `configs/portfolio_allocator_policy.json` base_env for breakdown sleeve.

---

### Task 1.2 — inplay_breakout: base signal quality check

**Code fix committed (96cf4fd)**: two new params fix ATR-scale mismatch.
First confirm the engine generates any signals at all without regime/dist filters:

```bash
BREAKOUT_REGIME_MODE=any \
BREAKOUT_SL_HTF_MULT=1.0 \
BREAKOUT_MAX_DIST_HTF_MULT=1.5 \
BREAKOUT_RR=3.0 \
BREAKOUT_ALLOW_LONGS=1 \
BREAKOUT_ALLOW_SHORTS=0 \
BACKTEST_CACHE_ONLY=0 \
python3 backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
  --strategies inplay_breakout \
  --days 365 --end 2025-12-31 \
  --tag breakout_htf_sl_probe_2025 \
  --starting_equity 100 --risk_pct 0.01 --leverage 1 \
  --fee_bps 6 --slippage_bps 2 \
  2>&1 | tee /tmp/breakout_htf_probe.log
```

Print summary: trades, PF, WR, max_dd, avg hold time.

If trades ≥ 15 and PF ≥ 1.0: proceed to mini-sweep (3×3×2 = 18 combos):

```bash
python3 << 'PYEOF'
import subprocess, itertools, csv, os, glob

params = {
    "BREAKOUT_SL_HTF_MULT":       ["0.8", "1.0", "1.5"],
    "BREAKOUT_MAX_DIST_HTF_MULT": ["1.0", "1.5", "2.0"],
    "BREAKOUT_RR":                ["2.5", "3.5"],
}
base_env = {
    "BREAKOUT_REGIME_MODE": "any",
    "BREAKOUT_ALLOW_LONGS": "1",
    "BREAKOUT_ALLOW_SHORTS": "0",
    "BACKTEST_CACHE_ONLY": "0",
}
keys = list(params.keys())
results = []
for combo in itertools.product(*params.values()):
    env = {**os.environ, **base_env, **dict(zip(keys, combo))}
    tag = "brk_htf_" + "_".join(v.replace(".","") for v in combo)
    cmd = [".venv/bin/python","backtest/run_portfolio.py",
           "--symbols","BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT",
           "--strategies","inplay_breakout",
           "--days","365","--end","2025-12-31","--tag",tag,
           "--starting_equity","100","--risk_pct","0.01",
           "--leverage","1","--fee_bps","6","--slippage_bps","2"]
    subprocess.run(cmd, env=env, capture_output=True, text=True, cwd="/root/by-bot")
    runs = sorted(glob.glob(f"/root/by-bot/backtest_runs/portfolio_*_{tag}"))
    if runs:
        sf = runs[-1]+"/summary.csv"
        if os.path.exists(sf):
            r = list(csv.DictReader(open(sf)))[0]
            t=int(r.get("trades",0)); pf=float(r.get("profit_factor",0))
            results.append({"p":dict(zip(keys,combo)),"t":t,"pf":pf,
                           "wr":float(r.get("winrate",0)),"dd":float(r.get("max_drawdown",0))})
results.sort(key=lambda x:x["pf"]*min(1,x["t"]/20),reverse=True)
print("inplay_breakout HTF-SL sweep results:")
for r in results:
    p=r["p"]
    print(f"  sl_htf={p['BREAKOUT_SL_HTF_MULT']} dist={p['BREAKOUT_MAX_DIST_HTF_MULT']} rr={p['BREAKOUT_RR']}"
          f" -> t={r['t']} PF={r['pf']:.3f} wr={r['wr']*100:.0f}% dd={r['dd']:.1f}%")
PYEOF
```

If best PF ≥ 1.25, trades ≥ 20: run WF-22 with best params, tag `breakout_wf22_htf`.

---

## DAY 2 — Elder v3 sweep + midterm v3 rehab

### Task 2.1 — Elder v3 macro-relaxation sweep (96 combos)

Already has autoresearch config. **DO NOT use cache_only if 0 trades.**

```bash
python3 scripts/run_dynamic_crypto_walkforward.py \
  --config configs/autoresearch/elder_ts_v3_macro_relax_v1.json \
  2>&1 | tee /tmp/elder_v3_sweep.log
```

Then analyze (full analysis script is in `CODEX_TASK_elder_v3_sweep_20260419.md`).

If best PF ≥ 1.25, trades ≥ 15: run WF-22 (see that task file for command).

---

### Task 2.2 — Midterm v3 trailing stop fix validation + mini sweep

The trailing stop bug was fixed (commit 3fd801f). Now validate the fix works and find
optimal entry params. Full task in `CODEX_TASK_midterm_v3_rehab_20260419.md`.

Quick smoke test first:
```bash
MTPB3_TRAIL_ATR_MULT=0 \
MTPB3_TIME_STOP_BARS_5M=576 \
MTPB3_USE_VOL_FILTER=0 \
MTPB3_USE_RSI_FILTER=0 \
BACKTEST_CACHE_ONLY=1 \
python3 backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
  --strategies btc_eth_midterm_v3 \
  --days 360 --end 2026-04-01 \
  --tag midterm_v3_fix_smoke \
  --starting_equity 100 --risk_pct 0.01 --leverage 1 \
  --fee_bps 6 --slippage_bps 2
```

If trades > 5 and hold time > 4h → proceed to 27-combo sweep (Task 2 in rehab task file).

---

## DAY 3 — ATT1 WF-22 + HZBO1 sweep + Alpaca sim + breakdown v2 diagnosis

### Task 3.1 — ATT1 WF-22

Best params from 254-run sweep (r136): PIVOT_LEFT=2, R=2, R2=0.9, TOUCH_ATR=0.25, RSI_L=52, RSI_S=40, PF=1.295.
Full task in `CODEX_TASK_att1_hzbo1_wf22_20260418.md`.

```bash
ATT1_PIVOT_LEFT=2 \
ATT1_R=2 \
ATT1_R2=0.9 \
ATT1_TOUCH_ATR=0.25 \
ATT1_RSI_LONG_MAX=52 \
ATT1_RSI_SHORT_MIN=40 \
ATT1_ALLOW_LONGS=1 \
ATT1_ALLOW_SHORTS=1 \
python3 scripts/run_crypto_core_walkforward.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,LTCUSDT \
  --strategies alt_trendline_touch_v1 \
  --end 2026-04-18 \
  --total_days 330 --window_days 15 --step_days 15 \
  --min_pf 1.20 --min_net 0.0 --max_dd 25.0 \
  --tag att1_wf22_r136 \
  2>&1 | tee /tmp/att1_wf22.log

WF_DIR=$(ls -1dt backtest_runs/walkforward_*_att1_wf22_r136 | head -1)
cat "$WF_DIR/walkforward_report.md"
```

Gate: AvgPF ≥ 1.20 → promote to bear_chop/bear_trend regime overlays.

---

### Task 3.2 — HZBO1 live bridge sweep (no cache)

```bash
python3 scripts/run_dynamic_crypto_walkforward.py \
  --config configs/autoresearch/hzbo1_live_bridge_v1_nocache.json \
  2>&1 | tee /tmp/hzbo1_live.log
```

Full analysis in `CODEX_TASK_att1_hzbo1_wf22_20260418.md`.

---

### Task 3.3 — Alpaca v37 universe research sim

```bash
cd /root/by-bot
source /root/by-bot/.venv/bin/activate
bash scripts/run_equities_monthly_v37_sim.sh 2>&1 | tee /tmp/alpaca_v37_sim.log
```

Full task in `CODEX_TASK_alpaca_universe_v37_sim_20260418.md`.

---

### Task 3.4 — Breakdown v2 diagnosis (why 0 trades)

```bash
# First try without cache to confirm it's not a data issue:
BREAKDOWN2_ALLOW_SHORTS=1 \
BREAKDOWN2_LOOKBACK_H=24 \
python3 backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT \
  --strategies alt_inplay_breakdown_v2 \
  --days 180 --end 2026-04-01 \
  --tag bd2_nocache_diag \
  --starting_equity 100 --risk_pct 0.01 --leverage 1 \
  --fee_bps 6 --slippage_bps 2

# If still 0 trades:
python3 -c "
import os
os.environ['BREAKDOWN2_ALLOW_SHORTS'] = '1'
# Run single-candle diagnostic to print no_signal_reason counts
"
# Check the no_signal_reason breakdown in trades.csv and any debug logs
```

Report: trades, most common no_signal_reason. If signal engine returns
`history_short` or `ltf_short` → cache gap. If `regime_block` or `impulse_weak`
→ parameter issue. Fix accordingly and add to 3.1 WF-22 if fixed.

---

## Success criteria summary

| Task | Gate for promotion |
|------|--------------------|
| 1.1 Breakdown v1 WF-22 | AvgPF ≥ 1.20 → enable in bear_chop + bear_trend |
| 1.2 inplay_breakout HTF sweep | PF ≥ 1.25 t≥20 → WF-22 → enable in bull_trend |
| 2.1 Elder v3 sweep | PF ≥ 1.25 t≥15 → WF-22 → enable ENABLE_ETS3_TRADING |
| 2.2 Midterm v3 rehab | WF-22 AvgPF ≥ 1.20 → update ENV defaults in strategy |
| 3.1 ATT1 WF-22 | AvgPF ≥ 1.20 → add to bear regime overlays |
| 3.2 HZBO1 sweep | PF ≥ 1.25 → WF-22 → promote to live |
| 3.3 Alpaca v37 sim | SR ≥ 1.0, DD < 15% → deploy to live monthly cycle |
| 3.4 Breakdown v2 diag | Fix signal → WF-22 → replace v1 if better |

## After each successful WF-22:

1. Update `configs/portfolio_allocator_policy.json` base_env with best params
2. Update relevant `configs/regime_overlay_*.env` with ENABLE flag + params
3. Update `scripts/build_regime_state.py` if any new ENV defaults needed
4. Commit with tag: `feat(STRATEGY): promote to production after WF-22`
5. Push: `git push origin codex/dynamic-symbol-filters`
