# Codex Task — Midterm v3 Strategy Rehabilitation (2026-04-19)

## Context & Root Cause

`btc_eth_midterm_v3` was getting stopped out within 10-30 minutes on every trade
despite being designed as a multi-day "midterm" strategy.

**Bug fixed in commit 3fd801f:**
- `trailing_atr_period` was 14 × 5m bars = 70-minute ATR (~$100-200 on BTC)
- Initial SL used 14 × 1H ATR (~$500-800)
- Trailing stop was 5-10× tighter than initial SL → immediate stop-out
- Fixed: `trail_atr_period_5m=168` (= 14h of 5m bars) and `time_stop_bars_5m=576` (48h)

**Smoke test with fix:**
- `MTPB3_TRAIL_ATR_MULT=0 MTPB3_TIME_STOP_BARS_5M=864` → PF=2.09 on 5 trades (BTC+ETH)
- Trades now hold 13-41 hours as expected

**Remaining problem:**
- Relaxed-filter test (no RSI/vol/fresh-touch filter): 32 trades, PF=0.591, WR=31%
- The EMA20 reclaim entry signal itself has poor quality
- Even best-filtered runs barely reach PF=0.977 (before the fix)
- Signal fires too rarely: ~2-5 trades/month on BTC+ETH with standard filters

## Goal

Increase trade frequency to 8-20 per month across BTC+ETH+alts **while** keeping
PF ≥ 1.25 over a 360-day backtest. The fix is already in — now we need better
signal quality.

Branch: `codex/dynamic-symbol-filters`

---

## Task 1 — Confirm the trailing-stop fix works

Run a fresh backtest with the fix and MACD-only filter (no RSI, no vol filter):

```bash
cd /root/by-bot
git pull origin codex/dynamic-symbol-filters
source .venv/bin/activate

MTPB3_TRAIL_ATR_MULT=0 \
MTPB3_TIME_STOP_BARS_5M=576 \
MTPB3_USE_VOL_FILTER=0 \
MTPB3_USE_RSI_FILTER=0 \
BACKTEST_CACHE_ONLY=1 \
python3 backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
  --strategies btc_eth_midterm_v3 \
  --days 360 \
  --end 2026-04-01 \
  --tag midterm_v3_macd_only_no_trail \
  --starting_equity 100 --risk_pct 0.01 --leverage 1 \
  --fee_bps 6 --slippage_bps 2
```

Print: trades, PF, WR, avg hold time.

---

## Task 2 — Focused parameter sweep (no trailing stop, wider time stop)

Test combinations of SL width, RR, and RSI thresholds to find the sweet spot:

```bash
python3 << 'PYEOF'
import subprocess, itertools, csv, os

params = {
    "MTPB3_SL_ATR_MULT": ["1.5", "2.0", "2.5"],
    "MTPB3_RR":           ["2.0", "2.5", "3.0"],
    "MTPB3_RSI_LONG_MAX": ["55", "60", "65"],
}
base_env = {
    "MTPB3_TRAIL_ATR_MULT": "0",
    "MTPB3_TIME_STOP_BARS_5M": "576",
    "MTPB3_USE_VOL_FILTER": "0",
    "BACKTEST_CACHE_ONLY": "1",
}

keys = list(params.keys())
results = []
for combo in itertools.product(*params.values()):
    env = {**os.environ, **base_env, **dict(zip(keys, combo))}
    tag = "mt3_sweep_" + "_".join(v.replace(".","") for v in combo)
    cmd = [
        ".venv/bin/python", "backtest/run_portfolio.py",
        "--symbols", "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT",
        "--strategies", "btc_eth_midterm_v3",
        "--days", "360", "--end", "2026-04-01",
        "--tag", tag,
        "--starting_equity", "100", "--risk_pct", "0.01",
        "--leverage", "1", "--fee_bps", "6", "--slippage_bps", "2",
    ]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd="/root/by-bot")
    # Find summary
    import glob
    runs = sorted(glob.glob(f"backtest_runs/portfolio_*_{tag}"))
    if runs:
        sf = runs[-1] + "/summary.csv"
        if os.path.exists(sf):
            row = list(csv.DictReader(open(sf)))[0]
            results.append({
                "params": dict(zip(keys, combo)),
                "trades": int(row.get("trades", 0)),
                "pf": float(row.get("profit_factor", 0)),
                "wr": float(row.get("winrate", 0)),
                "pnl": float(row.get("net_pnl", 0)),
                "dd": float(row.get("max_drawdown", 0)),
            })

results.sort(key=lambda x: x["pf"], reverse=True)
print(f"{'SL_ATR':8} {'RR':5} {'RSI_L':6} {'Trades':7} {'PF':6} {'WR%':6} {'PnL':7}")
for r in results[:15]:
    if r["trades"] >= 10:
        p = r["params"]
        print(f"{p['MTPB3_SL_ATR_MULT']:8} {p['MTPB3_RR']:5} {p['MTPB3_RSI_LONG_MAX']:6} "
              f"{r['trades']:7} {r['pf']:6.3f} {r['wr']*100:5.1f}% {r['pnl']:7.2f}")
PYEOF
```

---

## Task 3 — Test EMA level upgrade (EMA50 instead of EMA20 for pullback)

The EMA20 signal is too noisy. Try using EMA50 as the pullback level — this
catches deeper, more meaningful dips.

Edit `strategies/btc_eth_midterm_v3.py`, change:
```python
signal_ema_period: int = 20
```
to:
```python
signal_ema_period: int = 50
```

Then run:
```bash
MTPB3_TRAIL_ATR_MULT=0 \
MTPB3_TIME_STOP_BARS_5M=576 \
MTPB3_USE_VOL_FILTER=0 \
BACKTEST_CACHE_ONLY=1 \
python3 backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
  --strategies btc_eth_midterm_v3 \
  --days 360 --end 2026-04-01 \
  --tag midterm_v3_ema50_test \
  --starting_equity 100 --risk_pct 0.01 --leverage 1 \
  --fee_bps 6 --slippage_bps 2
```

Also try EMA50 with `MTPB3_SIGNAL_EMA_PERIOD=50` env override (if the strategy
supports it via `MTPB3_SIGNAL_EMA_PERIOD`) — check the strategy for the env var.

---

## Task 4 — WF-22 validation of best config

Take the best result from Task 2 (PF ≥ 1.25, trades ≥ 10):

```bash
# Example with best params — substitute actual best values:
MTPB3_SL_ATR_MULT=<best> \
MTPB3_RR=<best> \
MTPB3_RSI_LONG_MAX=<best> \
MTPB3_TRAIL_ATR_MULT=0 \
MTPB3_TIME_STOP_BARS_5M=576 \
MTPB3_USE_VOL_FILTER=0 \
python3 scripts/run_crypto_core_walkforward.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
  --strategies btc_eth_midterm_v3 \
  --end 2026-04-18 \
  --total_days 330 \
  --window_days 15 \
  --step_days 15 \
  --min_pf 1.20 --min_net 0.0 --max_dd 25.0 \
  --tag midterm_v3_wf22_best \
  2>&1 | tee /tmp/midterm_wf22.log

WF_DIR=$(ls -1dt backtest_runs/walkforward_*_midterm_v3_wf22_best | head -1)
cat "$WF_DIR/walkforward_report.md"
```

---

## Expected outcomes

| Scenario | Action |
|----------|--------|
| Task 2 finds config with PF ≥ 1.25, trades ≥ 8/month | Run WF-22 (Task 4) |
| Task 3 EMA50 test shows big improvement | Commit EMA change, add to sweep |
| WF-22 AvgPF ≥ 1.20 | Promote to production, set ENV defaults in strategy |
| WF-22 AvgPF 1.10-1.20 | Borderline — try adding back RSI filter with loose threshold |
| No config clears 1.20 PF | Midterm strategy needs deeper structural redesign (report findings) |

---

## Notes

- `BACKTEST_CACHE_ONLY=1` — only runs if candle data is cached. If 0 trades, check cache.
- Task 1 is quick sanity check (~2 min). Tasks 2-3 are the main work.
- The key ENV fix vars: `MTPB3_TRAIL_ATR_MULT=0` and `MTPB3_TIME_STOP_BARS_5M=576`
- Do NOT remove the trailing stop fix from the code (trail_atr_period_5m=168) —
  it's correct even if we keep trailing stops disabled by default in production.
- If Task 3 (EMA50) is clearly better, commit that change too.
