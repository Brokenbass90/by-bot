# Codex Task — ATT1 WF-22 Validation + HZBO1 Live Sweep (2026-04-18)

## Context

ATT1 initial parameter sweep (254 runs, cache-only) is complete.
Best candidate: **r136** — PF=1.295, WR=58%, MaxDD=10.2%, 255 trades.

Optimal parameters identified:
- `ATT1_PIVOT_LEFT=2`, `ATT1_PIVOT_RIGHT=2`
- `ATT1_MIN_PIVOTS=2`, `ATT1_MAX_PIVOT_AGE=20`
- `ATT1_MIN_R2=0.9`, `ATT1_TOUCH_ATR=0.25`
- `ATT1_RSI_LONG_MAX=52`, `ATT1_RSI_SHORT_MIN=40`

34 runs pass (PF>=1.20, DD<15%, trades>=200). The tight R2=0.9 + small pivots 
combo consistently outperforms.

HZBO1 status: only 6/22 windows pass WF gate (PF≥1.20) in both macro/no-macro
variants. Needs a parameter sweep on live data (cache_only=false).

---

## Task 1 — Run ATT1 focused sweep on live data

This validates whether the r136 regime holds on fresh 2026 data (not in cache).

```bash
cd /root/by-bot
git pull origin codex/dynamic-symbol-filters
source .venv/bin/activate

python3 scripts/run_dynamic_crypto_walkforward.py \
  --config configs/autoresearch/att1_focused_pivot_sweep_v2_nocache.json \
  2>&1 | tee /tmp/att1_focused_sweep.log
```

After run completes, find the best result:
```bash
python3 << 'PYEOF'
import csv, os, glob, itertools, json

with open('configs/autoresearch/att1_focused_pivot_sweep_v2_nocache.json') as f:
    cfg = json.load(f)

runs = sorted(glob.glob('backtest_runs/portfolio_*_att1_focused_pivot_sweep_v2_nocache_*'))
results = []
for r in runs:
    sf = os.path.join(r, 'summary.csv')
    if not os.path.exists(sf): continue
    with open(sf) as f:
        row = list(csv.DictReader(f))
    if not row: continue
    d = row[0]
    results.append({
        'dir': r,
        'trades': int(d.get('trades', 0)),
        'pf': float(d.get('profit_factor', 0)),
        'dd': float(d.get('max_drawdown', 0)),
        'pnl': float(d.get('net_pnl', 0)),
    })
results.sort(key=lambda x: x['pf'], reverse=True)
print(f"Total runs: {len(results)}, passing (PF>=1.20,DD<15%): {sum(1 for r in results if r['pf']>=1.20 and r['dd']<15)}")
for r in results[:5]:
    print(f"  PF={r['pf']:.3f} DD={r['dd']:.1f}% trades={r['trades']} pnl={r['pnl']:.2f}")
PYEOF
```

---

## Task 2 — ATT1 WF-22 walk-forward validation (optimal params from r136)

**Goal:** Run 22 rolling windows across the last 330 days with r136 params fixed.
Pass condition: AvgPF > 1.20 AND AvgDD < 25%.

```bash
cd /root/by-bot
source .venv/bin/activate

ATT1_PIVOT_LEFT=2 \
ATT1_PIVOT_RIGHT=2 \
ATT1_MIN_PIVOTS=2 \
ATT1_MAX_PIVOT_AGE=20 \
ATT1_MIN_R2=0.9 \
ATT1_TOUCH_ATR=0.25 \
ATT1_RSI_LONG_MAX=52 \
ATT1_RSI_SHORT_MIN=40 \
python3 scripts/run_crypto_core_walkforward.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,LTCUSDT,ADAUSDT,DOTUSDT,SUIUSDT \
  --strategies alt_trendline_touch_v1 \
  --end 2026-04-18 \
  --total_days 330 \
  --window_days 15 \
  --step_days 15 \
  --starting_equity 100 \
  --risk_pct 0.01 \
  --leverage 1 \
  --fee_bps 6 \
  --slippage_bps 2 \
  --min_pf 1.20 \
  --min_net 0.0 \
  --max_dd 25.0 \
  --tag att1_wf22_r136_optimal \
  2>&1 | tee /tmp/att1_wf22.log
```

After run, print the walkforward_report.md:
```bash
WF_DIR=$(ls -1dt backtest_runs/walkforward_*_att1_wf22_r136_optimal 2>/dev/null | head -1)
cat "$WF_DIR/walkforward_report.md"
```

**WF-22 PASS criteria:**
- AvgPF >= 1.20 AND AvgDD <= 25%: ✅ ATT1 gets PROMOTED to production
- Otherwise: note which windows fail and suggest parameter adjustments

---

## Task 3 — HZBO1 live bridge parameter sweep

HZBO1 current status: 6/22 windows pass (27%). The config for the live sweep
already exists in `configs/autoresearch/hzbo1_live_bridge_v1_nocache.json`.

```bash
cd /root/by-bot
source .venv/bin/activate

python3 scripts/run_dynamic_crypto_walkforward.py \
  --config configs/autoresearch/hzbo1_live_bridge_v1_nocache.json \
  2>&1 | tee /tmp/hzbo1_live_sweep.log
```

After run:
```bash
python3 << 'PYEOF'
import csv, os, glob

runs = sorted(glob.glob('backtest_runs/portfolio_*_hzbo1_live_bridge_v1_nocache_*'))
results = []
for r in runs:
    sf = os.path.join(r, 'summary.csv')
    if not os.path.exists(sf): continue
    with open(sf) as f:
        row = list(csv.DictReader(f))
    if not row: continue
    d = row[0]
    results.append({
        'pf': float(d.get('profit_factor', 0)),
        'dd': float(d.get('max_drawdown', 0)),
        'trades': int(d.get('trades', 0)),
        'pnl': float(d.get('net_pnl', 0)),
    })
results.sort(key=lambda x: x['pf'], reverse=True)
passing = [r for r in results if r['pf']>=1.20 and r['dd']<15]
print(f"HZBO1 live sweep: {len(results)} runs, {len(passing)} pass (PF>=1.20, DD<15%)")
for r in results[:8]:
    flag = '✓' if r['pf']>=1.20 and r['dd']<15 else '✗'
    print(f"  {flag} PF={r['pf']:.3f} DD={r['dd']:.1f}% trades={r['trades']}")
PYEOF
```

---

## Expected outcomes & decisions

| Result | Action |
|--------|--------|
| ATT1 WF-22 AvgPF >= 1.20 | Promote to production: set optimal ENV defaults in `alt_trendline_touch_v1.py` |
| ATT1 WF-22 AvgPF 1.10-1.20 | Borderline: try relaxing RSI thresholds (+3), rerun WF |
| ATT1 WF-22 AvgPF < 1.10 | Keep in rehab, try more `--min_pf 1.05` threshold |
| HZBO1 sweep top-5 PF >= 1.25 | Build WF-22 for best HZBO1 params |
| HZBO1 sweep top-5 PF < 1.20 | HZBO1 is marginally viable — mark as bear-only sleeve only |

---

## Notes
- Run Tasks 1, 2, 3 in sequence (1 takes ~20 min, 2 takes ~30 min, 3 takes ~20 min)
- Tasks 1 and 3 use cache_only=false → will fetch fresh Bybit candles (~1.5s/call)
- Do NOT commit any data cache files
- If ATT1 WF-22 passes, write a summary commit updating the env defaults in
  `strategies/alt_trendline_touch_v1.py` with the validated optimal params as comments
