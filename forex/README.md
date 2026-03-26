# Forex Pilot (Isolated Module)

This directory is intentionally isolated from crypto runtime/backtest code.

## Scope
- Research-only Forex backtests.
- Separate spread/swap/session modeling.
- No imports from `smart_pump_reversal_bot.py` and no changes to live crypto flow.

## Current Components
- `forex/data.py`: M5 CSV loader.
- `forex/engine.py`: simple backtest engine (`spread + daily swap`).
- `forex/strategies/trend_retest_session_v1.py`: trend breakout/retest.
- `forex/strategies/range_bounce_session_v1.py`: sideways bounce/rejection.
- `forex/strategies/breakout_continuation_session_v1.py`: momentum breakout continuation.
- `forex/strategies/grid_reversion_session_v1.py`: grid-like mean reversion to EMA.
- `forex/strategies/liquidity_sweep_bounce_session_v1.py`: false-break liquidity sweep with reclaim back inside recent range.
- `forex/strategies/trend_pullback_rebound_v1.py`: trend pullback rebound.
- `scripts/run_forex_backtest.py`: CLI runner.
- `scripts/run_forex_pilot_smoke.sh`: smoke wrapper.
- `scripts/run_forex_pilot_batch.sh`: batch runner for EURUSD/GBPUSD/USDJPY.
- `scripts/run_forex_multi_strategy_gate.py`: pair+strategy gate scanner.
- `scripts/run_forex_multi_strategy_gate.sh`: shell wrapper for multi-strategy gate.

## Expected Input CSV
Headers:
- `ts,o,h,l,c,v`
or
- `timestamp,open,high,low,close,volume`

Timestamp can be seconds or milliseconds.

## Smoke Run
```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

FX_SYMBOL=EURUSD \
FX_CSV_PATH=data_cache/forex/EURUSD_M5.csv \
FX_SPREAD_PIPS=1.2 \
FX_SWAP_LONG_PIPS_DAY=-0.2 \
FX_SWAP_SHORT_PIPS_DAY=-0.2 \
bash scripts/run_forex_pilot_smoke.sh
```

## Batch Run (EURUSD, GBPUSD, USDJPY)
```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

FX_DATA_DIR=data_cache/forex \
FX_PAIRS=EURUSD,GBPUSD,USDJPY \
FX_SESSION_START_UTC=6 \
FX_SESSION_END_UTC=20 \
bash scripts/run_forex_pilot_batch.sh
```

## Strategy Scan (Preset Grid)
Runs 3 presets (`conservative`, `balanced`, `active`) per pair and builds ranked summary.

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

FX_DATA_DIR=data_cache/forex \
FX_PAIRS=EURUSD,GBPUSD,USDJPY \
FX_SESSION_START_UTC=6 \
FX_SESSION_END_UTC=20 \
bash scripts/run_forex_strategy_scan.sh
```

## Data Readiness Check
```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

FX_DATA_DIR=data_cache/forex \
FX_PAIRS=EURUSD,GBPUSD,USDJPY \
bash scripts/run_forex_data_check.sh
```

This writes `docs/forex_data_status.csv` with:
- file presence
- row count
- first/last timestamp
- median candle step (to detect non-M5 data)

## Import Broker CSV (MT5/Generic)
If your source CSV is not in `ts,o,h,l,c,v`, convert it first:

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

python3 scripts/forex_import_csv.py \
  --input /path/to/EURUSD_M5_export.csv \
  --output data_cache/forex/EURUSD_M5.csv \
  --symbol EURUSD \
  --tz_offset_hours 0
```

Then run:

```bash
FX_DATA_DIR=data_cache/forex \
FX_PAIRS=EURUSD,GBPUSD,USDJPY \
bash scripts/run_forex_data_check.sh
```

## Batch Import (3 pairs at once)
Set source files in env and run one command:

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

FX_PAIRS=EURUSD,GBPUSD,USDJPY \
FX_IMPORT_TZ_OFFSET_HOURS=0 \
FX_EURUSD_SRC="/absolute/path/to/EURUSD_M5_export.csv" \
FX_GBPUSD_SRC="/absolute/path/to/GBPUSD_M5_export.csv" \
FX_USDJPY_SRC="/absolute/path/to/USDJPY_M5_export.csv" \
bash scripts/run_forex_import_batch.sh
```

Then:

```bash
FX_DATA_DIR=data_cache/forex \
FX_PAIRS=EURUSD,GBPUSD,USDJPY \
bash scripts/run_forex_data_check.sh

FX_DATA_DIR=data_cache/forex \
FX_PAIRS=EURUSD,GBPUSD,USDJPY \
bash scripts/run_forex_strategy_scan.sh
```

## MT5 Quick Export (No History Center Menu Needed)
If your MT5 build does not show "History Center", use the bundled script:

1. In MT5: `File -> Open Data Folder`.
2. Open `MQL5/Scripts`.
3. Copy this file there:
   - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/forex/mt5/ExportForexM5Batch.mq5`
4. In MT5 Navigator: right-click `Scripts` -> `Refresh`.
5. Drag `ExportForexM5Batch` onto any chart and press `OK`.
6. CSV files will be created in `MQL5/Files` (inside MT5 data folder):
   - `EURUSD_M5.csv`, `GBPUSD_M5.csv`, `EURJPY_M5.csv`, `USDJPY_M5.csv`, `AUDJPY_M5.csv`, `USDCAD_M5.csv`, `GBPJPY_M5.csv`.

Then copy those CSV files to project input folder and run import:

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

mkdir -p data_in/forex_mt5
# copy *.csv from MT5 MQL5/Files into data_in/forex_mt5 first

FX_IMPORT_AUTODISCOVER=1 \
FX_IMPORT_SEARCH_ROOTS="/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/data_in/forex_mt5" \
FX_IMPORT_TZ_OFFSET_HOURS=2 \
FX_PAIRS=EURUSD,GBPUSD,EURJPY,USDJPY,AUDJPY,USDCAD,GBPJPY \
bash scripts/run_forex_import_batch.sh

FX_DATA_DIR=data_cache/forex \
FX_PAIRS=EURUSD,GBPUSD,EURJPY,USDJPY,AUDJPY,USDCAD,GBPJPY \
bash scripts/run_forex_data_check.sh
```

## Walk-Forward Stability Check
Check stability by month/week/rolling windows for one pair/preset.

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

python3 scripts/run_forex_walkforward.py \
  --symbol GBPUSD \
  --csv data_cache/forex/GBPUSD_M5.csv \
  --preset conservative \
  --mode monthly \
  --spread_pips 1.2 \
  --swap_long -0.4 \
  --swap_short -0.4 \
  --session_start_utc 6 \
  --session_end_utc 20

python3 scripts/run_forex_walkforward.py \
  --symbol GBPUSD \
  --csv data_cache/forex/GBPUSD_M5.csv \
  --preset conservative \
  --mode rolling \
  --window_days 28 \
  --step_days 7 \
  --spread_pips 1.2 \
  --swap_long -0.4 \
  --swap_short -0.4 \
  --session_start_utc 6 \
  --session_end_utc 20
```

## Combo Walk-Forward (Any `pair+strategy:preset`)
Use this for full production combos (not only trend-retest), with base+stress per segment.

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

python3 scripts/run_forex_combo_walkforward.py \
  --symbol GBPUSD \
  --csv data_cache/forex/GBPUSD_M5.csv \
  --strategy trend_retest_session_v1:conservative \
  --mode rolling \
  --window_days 28 \
  --step_days 7

python3 scripts/run_forex_combo_walkforward.py \
  --symbol EURJPY \
  --csv data_cache/forex/EURJPY_M5.csv \
  --strategy grid_reversion_session_v1:eurjpy_canary \
  --mode rolling \
  --window_days 28 \
  --step_days 7
```

## News Blackout Study
Use this when you have a normalized historical macro-event CSV and want a like-for-like `baseline vs news-aware` comparison on the same combo walk-forward path.

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

FX_SYMBOL=GBPJPY \
FX_STRATEGY=trend_retest_session_v2:conservative \
FX_SESSION_START_UTC=6 \
FX_SESSION_END_UTC=14 \
FX_NEWS_EVENTS_CSV=runtime/news_filter/events_latest.csv \
FX_NEWS_POLICY_JSON=configs/news_filter_policy.example.json \
bash scripts/run_forex_news_blackout_study.sh
```

Outputs:
- baseline monthly + rolling combo walk-forward summaries
- news-aware monthly + rolling combo walk-forward summaries
- per-segment `news_blocked_signals` counts for the news-aware runs

## Trend Router Probe (`pair x preset x session-window`)
Use this when trend-family edge is clearly pair/session dependent and you want a structured search instead of manual trial-and-error.

The probe works in two stages:
- full-history ranking across `pair x strategy:preset x session-window`
- optional monthly + rolling walk-forward only for top candidates

Fast ranking only:
```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

python3 scripts/run_forex_trend_router_probe.py \
  --pairs GBPJPY,AUDJPY,USDJPY,EURJPY \
  --strategies trend_retest_session_v1:conservative,trend_retest_session_v1:gbpjpy_stability_a,trend_retest_session_v2:conservative,trend_retest_session_v2:gbpjpy_core \
  --session-windows 05-13,06-14,07-15,08-16 \
  --top-n-wf 0 \
  --tag fx_trend_router_fast
```

Full staged probe with walk-forward on top candidates:
```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

python3 scripts/run_forex_trend_router_probe.py \
  --pairs GBPJPY,AUDJPY,USDJPY,EURJPY,GBPUSD,EURUSD \
  --strategies trend_retest_session_v1:conservative,trend_retest_session_v1:gbpjpy_stability_a,trend_retest_session_v1:gbpjpy_stability_b,trend_retest_session_v2:conservative,trend_retest_session_v2:gbpjpy_core \
  --session-windows 05-13,06-14,07-15,06-20,08-16 \
  --top-n-wf 8 \
  --tag fx_trend_router
```

Outputs:
- `raw_runs.csv`: all full-history base/stress runs
- `ranked_summary.csv`: combined ranking with monthly/rolling fields
- `selected_best_per_pair.csv`: best candidate per pair after ranking

Recommended workflow:
- start with `--top-n-wf 0` to avoid expensive walk-forward on weak combos
- inspect `ranked_summary.csv`
- rerun with non-zero `--top-n-wf` only on the narrowed session/preset grid
- carry only the best router outputs into combo state / live filter work

## Dynamic Pair Gate (Universe Filter)
Scan many pairs and keep only those that pass both base and stress criteria.

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

python3 scripts/run_forex_universe_gate.py \
  --pairs EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY \
  --presets conservative \
  --data-dir data_cache/forex \
  --session-start-utc 6 \
  --session-end-utc 20 \
  --min-base-net 0 \
  --min-stress-net 0 \
  --min-trades 40 \
  --max-stress-dd 300 \
  --recent-days 28 \
  --min-recent-base-net 0 \
  --min-recent-stress-net 0 \
  --min-recent-trades 8 \
  --top-n 6 \
  --tag fx_gate
```

Outputs:
- `raw_runs.csv` (all base/stress runs)
- `gated_summary.csv` (pass/fail matrix + recent-window metrics)
- `selected_pairs.txt` (comma-separated active universe)

Recent-window gate protects from stale winners:
- `recent-days`: lookback window in days (set `0` to disable).
- `min-recent-base-net`, `min-recent-stress-net`: minimum net pips in recent window.
- `min-recent-trades`: minimum recent trade count.

## One-Command Dynamic Refresh (Fetch + Gate + Latest Outputs)
```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

FX_PAIRS=EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY \
FX_YF_PERIOD=60d \
FX_YF_INTERVAL=5m \
FX_MIN_BASE_NET=0 \
FX_MIN_STRESS_NET=0 \
FX_MIN_TRADES=40 \
FX_MAX_STRESS_DD=300 \
FX_RECENT_DAYS=28 \
FX_MIN_RECENT_BASE_NET=0 \
FX_MIN_RECENT_STRESS_NET=0 \
FX_MIN_RECENT_TRADES=8 \
FX_TOP_N=6 \
FX_GATE_TAG=fx_gate_dynamic \
bash scripts/run_forex_dynamic_gate.sh
```

Latest snapshots are copied to:
- `docs/forex_selected_pairs_latest.txt`
- `docs/forex_selected_pairs_latest.csv`
- `docs/forex_gate_latest.csv`
- `docs/forex_gate_raw_latest.csv`

## Multi-Strategy Pair+Strategy Gate
```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

FX_PAIRS=EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY \
FX_STRATEGIES=trend_retest_session_v1,range_bounce_session_v1,breakout_continuation_session_v1,grid_reversion_session_v1,trend_pullback_rebound_v1 \
FX_MIN_BASE_NET=0 \
FX_MIN_STRESS_NET=0 \
FX_MIN_TRADES=40 \
FX_MAX_STRESS_DD=300 \
FX_MIN_RECENT_STRESS_NET=0 \
FX_MIN_RECENT_TRADES=8 \
FX_TOP_N=12 \
FX_GATE_TAG=fx_multi_gate \
bash scripts/run_forex_multi_strategy_gate.sh
```

By default wrapper also runs combo state update after gate (`FX_UPDATE_STATE_AFTER_GATE=1`).
Disable if needed:
```bash
FX_UPDATE_STATE_AFTER_GATE=0 bash scripts/run_forex_multi_strategy_gate.sh
```

State update now also exports ready-to-use live filters to `docs/`:
- `forex_live_filter_latest.csv`
- `forex_live_filter_latest.json`
- `forex_live_filter_latest.env`
- `forex_live_active_combos_latest.txt`
- `forex_live_canary_combos_latest.txt`

Manual refresh command:
```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate
FX_GATED_CSV=backtest_runs/<your_gate_run>/gated_summary.csv bash scripts/run_forex_combo_state.sh
```

### Strategy Preset Syntax
You can pass strategy presets as `strategy:preset`:
- `trend_retest_session_v1:default|conservative|balanced|active|eurusd_canary`
- `range_bounce_session_v1:default|loose`
- `breakout_continuation_session_v1:default|strict|active`
- `grid_reversion_session_v1:default|strict|active|eurjpy_canary`
- `trend_pullback_rebound_v1:default|strict`

`eurjpy_canary` (grid) and `eurusd_canary` (trend-retest) are pair-specific tuned profiles and should be treated as `CANARY` until they pass full daily gate streaks.

Example:
```bash
FX_STRATEGIES=trend_retest_session_v1:conservative,grid_reversion_session_v1:active,breakout_continuation_session_v1:strict \
bash scripts/run_forex_multi_strategy_gate.sh
```

Fast pass (for quick iteration):
```bash
FX_MAX_BARS=2500 \
FX_MIN_TRADES=20 \
bash scripts/run_forex_multi_strategy_gate.sh
```

## Combo State Machine (ACTIVE / CANARY / BANNED)
After gate run, update persistent state of `pair+strategy` combos with streak logic:
- pass streak promotes `CANARY -> ACTIVE`
- fail streak bans `ACTIVE/CANARY -> BANNED`
- cooldown controls when banned combos can re-enter canary
- max active quota keeps only top-N active combos by stress net

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

# Uses latest backtest_runs/forex_multi_strategy_gate_*/gated_summary.csv by default
bash scripts/run_forex_combo_state.sh
```

Optional controls:
```bash
FX_GATED_CSV=backtest_runs/forex_multi_strategy_gate_fx_multi_gate_YYYYMMDD_HHMMSS/gated_summary.csv \
FX_PASS_STREAK_TO_ACTIVE=2 \
FX_FAIL_STREAK_TO_BAN=2 \
FX_COOLDOWN_DAYS=7 \
FX_MAX_ACTIVE_COMBOS=3 \
bash scripts/run_forex_combo_state.sh
```

Outputs:
- `docs/forex_combo_state_latest.csv` (all combos + current state + streaks)
- `docs/forex_combo_actions_latest.csv` (state transitions on this run)
- `docs/forex_combo_active_latest.csv` (active trading combos)
- `docs/forex_combo_active_latest.txt` (comma list: `PAIR@strategy`)

## Two-Stage Gate (Fast Scout -> Full Confirm -> State Update)
Use this to avoid overfitting to short windows:

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

bash scripts/run_forex_two_stage_gate.sh
```

It runs:
1. fast scan with `FX_FAST_MAX_BARS` (default `4500`)
2. full-history confirm on top fast candidates
3. state update from full confirm only

## Auto-Fetch From Yahoo (No Manual CSV Paths)
If you do not have broker exports yet, fetch intraday data directly:

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

pip install yfinance pandas

FX_PAIRS=EURUSD,GBPUSD,USDJPY \
FX_YF_PERIOD=60d \
FX_YF_INTERVAL=5m \
FX_DATA_DIR=data_cache/forex \
bash scripts/run_forex_fetch_yf.sh

FX_DATA_DIR=data_cache/forex \
FX_PAIRS=EURUSD,GBPUSD,USDJPY \
bash scripts/run_forex_data_check.sh

FX_DATA_DIR=data_cache/forex \
FX_PAIRS=EURUSD,GBPUSD,USDJPY \
bash scripts/run_forex_strategy_scan.sh
```

## Broker-Grade Fetch (OANDA API, Year+)
Use this for long-horizon M5 testing (365+ days), instead of Yahoo short intraday window.

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

export OANDA_API_TOKEN="YOUR_OANDA_TOKEN"
export OANDA_API_URL="https://api-fxpractice.oanda.com"   # practice
# export OANDA_API_URL="https://api-fxtrade.oanda.com"    # real

FX_PAIRS=EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY \
FX_DAYS=365 \
FX_GRANULARITY=M5 \
FX_DATA_DIR=data_cache/forex \
bash scripts/run_forex_fetch_oanda.sh

FX_DATA_DIR=data_cache/forex \
FX_PAIRS=EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY \
bash scripts/run_forex_data_check.sh
```

If you accidentally leave placeholder token (`YOUR_TOKEN` / `YOUR_OANDA_TOKEN`), script exits immediately with a clear message.

## Next Steps
1. Run overnight full-history multi-strategy gate (all 5 strategies) and compare with fast-pass shortlist.
2. Add broker-grade data source (MT5/OANDA/Dukascopy) for 12+ months M5 validation.
3. Add session-specific performance report (London/NY/Asia) and auto-disable on recent degradation.
