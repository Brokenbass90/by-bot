# Codex Task — Alpaca Universe v37 Research Sim (2026-04-18)

## Goal
Fetch OHLC data for 12 new tickers added in universe v37, then run the
full equities monthly research sim with the expanded 57-ticker universe
(2024-01-01 → today). Commit results so the web dashboard picks them up.

Branch: `codex/dynamic-symbol-filters`  
Commit that added the changes: `07c9489`

---

## Context

Universe was expanded from 44 → 57 tickers.  
New tickers missing from `data_cache/equities_1h/`:
```
TSM  QCOM  TXN  NOW  INTU  ADSK  WFC  SCHW  REGN  ISRG  PG  KO
```
(TSLA is already cached)

The research sim reads from `data_cache/equities_1h/` using `_M5.csv`
file naming (output of `fetch_equities_yfinance.py`).

---

## Steps

### 1. Git pull
```bash
cd /root/by-bot
git pull origin codex/dynamic-symbol-filters
source .venv/bin/activate
```

### 2. Fetch data for the 12 missing tickers (730d / 60m)
```bash
EQ_TICKERS="TSM,QCOM,TXN,NOW,INTU,ADSK,WFC,SCHW,REGN,ISRG,PG,KO,SPY,QQQ" \
EQ_YF_PERIOD="730d" \
EQ_YF_INTERVAL="60m" \
EQ_DATA_DIR="data_cache/equities_1h" \
bash scripts/run_equities_fetch_yf.sh
```

Verify 12+ new files appeared:
```bash
ls data_cache/equities_1h/TSM_M5.csv data_cache/equities_1h/QCOM_M5.csv \
   data_cache/equities_1h/TXN_M5.csv data_cache/equities_1h/NOW_M5.csv
```

### 3. Fetch updated earnings dates for all 57 tickers
```bash
EQ_TICKERS="AAPL,ADBE,AMD,AMZN,AVGO,CRWD,GOOGL,JPM,META,MSFT,NFLX,NVDA,ORCL,PANW,PLTR,TSLA,UBER,XOM,CRM,COIN,SHOP,SQ,SNOW,NET,DDOG,MDB,ABNB,GS,V,MA,BAC,CVX,CAT,GE,LMT,UNH,LLY,ABBV,JNJ,MRK,COST,WMT,HD,NKE,SBUX,TSM,QCOM,TXN,NOW,INTU,ADSK,WFC,SCHW,REGN,ISRG,PG,KO" \
EQ_EARNINGS_LIMIT="24" \
EQ_EARNINGS_OUT_CSV="data_cache/equities/earnings_dates.csv" \
bash scripts/run_equities_fetch_earnings_yf.sh
```

### 4. Run the full v36 refresh (research sim + live cycle builder)
```bash
bash scripts/run_equities_monthly_v36_refresh.sh 2>&1 | tee /tmp/eq_v37_sim.log
```

Expected runtime: 5–15 minutes depending on universe size.

Check for errors at the end:
```bash
tail -30 /tmp/eq_v37_sim.log
```

### 5. Verify outputs
```bash
# Research sim picks (should have trades across 2024-2026)
head -5 runtime/equities_monthly_v36/latest_picks.csv
wc -l runtime/equities_monthly_v36/latest_picks.csv

# Current cycle picks (today's recommendations)
cat runtime/equities_monthly_v36/current_cycle_picks.csv

# Summary metrics
cat runtime/equities_monthly_v36/latest_summary.csv | python3 -c "
import csv, sys
rows = list(csv.DictReader(sys.stdin))
for r in rows[-5:]:
    print(r)
"
```

### 6. Report results
Print to stdout:
- Total trades in latest_picks.csv
- Sharpe / total return from latest_summary.csv
- current_cycle_picks.csv (today's picks with weights)
- Any tickers that had 0 appearances despite being in universe
- Any errors in /tmp/eq_v37_sim.log

---

## Notes
- The fetch script always writes `{TICKER}_M5.csv` regardless of interval —
  that's normal, it's a legacy naming convention in this codebase.
- `BACKTEST_CACHE_ONLY` is NOT set here, so yfinance will be called live.
- If yfinance rate-limits on TSM (Taiwan exchange), retry after 60s or skip it
  and note in report.
- Sector cap = 2 per sector, earnings blackout = 3 days before / 1 day after.
- Do NOT commit data cache files (they're gitignored). Only commit if
  any source .py/.sh needed a bug fix during this task.
