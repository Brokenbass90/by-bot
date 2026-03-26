# Forex Demo Launch Plan (Latest)

## Current Decision
- AUTO demo-live: not approved yet (long robust passes = 0).
- Canary demo-live: allowed in low-risk mode with one active combo.

## Current Active/Canary
- ACTIVE: GBPJPY@trend_retest_session_v1:conservative
- CANARY: AUDJPY@grid_reversion_session_v1:eurjpy_canary

## Why this mode
- Short-window edge exists for several combos.
- Long-window stress robustness is not yet confirmed.
- Goal now: gather clean forward demo trades while preserving capital.

## Execution Mode (Recommended)
- max active combos: 1
- canary risk multiplier: 0.50
- per-trade risk base: 0.5% (effective 0.25% on canary)
- no leverage scaling until >= 2 independent long-robust combos

## Daily Cycle
1) Refresh gate in demo profile.
2) Export live filter env.
3) Run active health check.
4) Keep/deactivate by rules below.

## Keep/Deactivate Rules
- KEEP if all true:
  - rolling both-positive share >= 55% (for single-combo canary mode temporarily allow >= 50%)
  - stress total > 0
  - recent stress net >= -150 pips
- DEACTIVATE if any true:
  - stress return pct < 0 for 2 consecutive daily cycles
  - rolling both-positive share < 45%
  - stress DD breach > configured cap

## Command Block
```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate

FX_GATE_TAG=fx_demo_canary \
FX_FULL_MAX_BARS=15000 \
FX_FULL_MIN_TRADES=40 \
FX_FULL_MIN_STRESS_RETURN_PCT_EST=0 \
FX_FULL_MIN_RECENT_STRESS_NET=-150 \
FX_PASS_STREAK_TO_ACTIVE=1 \
FX_FAIL_STREAK_TO_BAN=3 \
FX_MAX_ACTIVE_COMBOS=1 \
FX_MAX_ACTIVE_PER_PAIR=1 \
FX_CANARY_RISK_MULT=0.50 \
bash scripts/run_forex_demo_canary_cycle.sh

python3 scripts/run_forex_active_health_check.py \
  --active-combos-txt docs/forex_combo_active_latest.txt \
  --data-dir data_cache/forex \
  --window-days 28 \
  --step-days 7 \
  --session-start-utc 6 \
  --session-end-utc 20 \
  --stress-spread-mult 1.8 \
  --stress-swap-mult 2.0 \
  --min-both-positive-share-pct 55 \
  --min-total-stress-pips 0 \
  --out-prefix docs/forex_active_health_latest
```
