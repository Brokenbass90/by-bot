# Codex Task — Elder v3 Macro-Relaxation Sweep (2026-04-19)

## Context

Elder Triple Screen v3 (`elder_triple_screen_v3`) had 0 trades with default macro
filter settings (`ETS3_MACRO_SLOPE_MIN_PCT=0.05`, `ETS3_MACRO_GAP_MIN_PCT=0.30`).

Smoke test with relaxed thresholds:
- `ETS3_MACRO_SLOPE_MIN_PCT=0.01, ETS3_MACRO_GAP_MIN_PCT=0.05`
- Result: 7 trades, PF=2.715, WR=71%, MaxDD=0.67%, +2.09%

The strategy is highly promising but over-filtered. Need to find the optimal
macro threshold balance that gives ≥15 trades/year with PF≥1.25.

Branch: `codex/dynamic-symbol-filters` (pull before running)

---

## Step 1 — Run the autoresearch sweep

```bash
cd /root/by-bot
git pull origin codex/dynamic-symbol-filters
source .venv/bin/activate

python3 scripts/run_dynamic_crypto_walkforward.py \
  --config configs/autoresearch/elder_ts_v3_macro_relax_v1.json \
  2>&1 | tee /tmp/elder_v3_sweep.log
```

96 combinations. With cache_only=true this should run in ~10-20 minutes.

---

## Step 2 — Analyze results

```bash
python3 << 'PYEOF'
import csv, os, glob, json, itertools

with open('configs/autoresearch/elder_ts_v3_macro_relax_v1.json') as f:
    cfg = json.load(f)

grid = cfg['grid']
keys = list(grid.keys())
values = [grid[k] for k in keys]
combos = list(itertools.product(*values))

runs = sorted(glob.glob('backtest_runs/portfolio_*_elder_ts_v3_macro_relax_v1_*'))
results = []
for r in runs:
    sf = os.path.join(r, 'summary.csv')
    if not os.path.exists(sf): continue
    with open(sf) as f:
        row = list(csv.DictReader(f))
    if not row: continue
    d = row[0]
    rid = r.split('_')[-1]
    n = int(rid[1:]) - 1
    combo = combos[n] if n < len(combos) else None
    pf = float(d.get('profit_factor', 0))
    trades = int(d.get('trades', 0))
    if pf >= 1.20 and trades >= 5:
        results.append({'run': rid, 'pf': pf, 'trades': trades,
                        'pnl': float(d.get('net_pnl', 0)),
                        'dd': float(d.get('max_drawdown', 0)),
                        'wr': float(d.get('winrate', 0)),
                        'params': dict(zip(keys, combo)) if combo else {}})

results.sort(key=lambda x: (x['pf'] * min(1, x['trades']/15)), reverse=True)
print(f"Qualifying (PF>=1.20, trades>=5): {len(results)}")
print()
print("Top 10 (ranked by PF × min(1, trades/15)):")
for r in results[:10]:
    p = r['params']
    print(f"  {r['run']:6s} PF={r['pf']:.3f} trades={r['trades']:3d} wr={r['wr']*100:.0f}% "
          f"dd={r['dd']:.1f}% slope={p.get('ETS3_MACRO_SLOPE_MIN_PCT','?')} "
          f"gap={p.get('ETS3_MACRO_GAP_MIN_PCT','?')} "
          f"rr={p.get('ETS3_RR','?')}")
PYEOF
```

---

## Step 3 — WF-22 for best config (if trades ≥ 15)

If any config has PF ≥ 1.25 with ≥ 15 trades in 360d:

```bash
# Replace with actual best values:
ETS3_MACRO_SLOPE_MIN_PCT=<best> \
ETS3_MACRO_GAP_MIN_PCT=<best> \
ETS3_MACRO_SLOPE_BARS=<best> \
ETS3_RR=<best> \
python3 scripts/run_crypto_core_walkforward.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,LTCUSDT \
  --strategies elder_triple_screen_v3 \
  --end 2026-04-18 \
  --total_days 330 --window_days 15 --step_days 15 \
  --min_pf 1.20 --min_net 0.0 --max_dd 25.0 \
  --tag elder_v3_wf22_best \
  2>&1 | tee /tmp/elder_v3_wf22.log

WF_DIR=$(ls -1dt backtest_runs/walkforward_*_elder_v3_wf22_best | head -1)
cat "$WF_DIR/walkforward_report.md"
```

---

## Expected outcomes

| Result | Action |
|--------|--------|
| WF-22 AvgPF ≥ 1.20, trades ≥ 8/window | Promote to production, update strategy ENV defaults |
| Best config PF ≥ 1.25 but trades < 8/window | Deploy as rare high-conviction signal, lower risk_pct |
| No config reaches PF ≥ 1.20 | Report best params found, Elder v3 needs signal redesign |

---

## Notes

- Elder v3 is in the `elder_ts_v3` sleeve, `ENABLE_ELDER_TS_V3_TRADING` env var
- The strategy uses v3 with `ETS3_*` prefix (not `ETS2_*`)
- If WF-22 passes, add to `configs/portfolio_allocator_policy.json` as a promoted sleeve
  and update `scripts/build_regime_state.py` with the optimal ENV defaults
