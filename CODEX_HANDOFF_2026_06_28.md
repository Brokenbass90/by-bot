# CODEX HANDOFF — 2026-06-28

Branch: `codex/dynamic-symbol-filters`

Workspace: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28`

Server: `root@64.226.73.119`, live path `/root/by-bot`

## Operating principle

Do not blindly unfreeze crypto risk. Current path remains:

1. execution-accurate replay;
2. DD/monthly/side/symbol forensics;
3. shadow or signal-only observation;
4. tiny canary with expiry and auto-rollback;
5. only then raise risk.

The owner wants a real diversified crypto package: short-only, range/chop, and later long-only sleeves, enough frequency to learn from live behavior, no multi-day silent freeze without incident analytics.

## Local web/dashboard fix

Problem:

- owner opened `http://127.0.0.1:8765` and saw `ERR_CONNECTION_REFUSED`;
- terminal logs were from a different Node project on `localhost:3000` (`Email Studio Demo`), not the bot web;
- bot web is FastAPI/uvicorn on `127.0.0.1:8765`, launched by `scripts/run_web.sh`;
- `.env.local` enables `WEB_LIVE_SYNC=1`, and `scripts/run_web.sh` could block on the initial SSH mirror sync before uvicorn started.

Fix:

- `scripts/run_web.sh` now preserves explicit CLI env overrides after sourcing `.env`/`.env.local`;
- initial live mirror sync is now backgrounded, so uvicorn starts immediately even if SSH sync is slow/stuck.

Verified locally:

```bash
bash -n scripts/run_web.sh
curl -s http://127.0.0.1:8765/ping
```

Result:

```json
{"pong": true}
```

Current listener observed:

- `Python ... TCP 127.0.0.1:8765 (LISTEN)`.

Owner should refresh: `http://127.0.0.1:8765/`.

## New research-only strategy: ARF2

New file:

- `strategies/alt_resistance_fade_v2.py`

Purpose:

- rebuild the short resistance-fade / range-pila sleeve using real repeated resistance clusters, not `max(highs[-N])`;
- test the user's manual-trading premise that levels need context: multiple touches, volume-at-price memory, VWAP/HVN confluence, rejection candle, risk geometry.

Important:

- this is research-only;
- no live monolith integration;
- no live risk unpause;
- namespace is `ARF2_*`, separate from ARF1.

Implemented logic:

- short-only;
- 4H probabilistic regime score instead of hard 6-gate filter;
- optional daily filter, default off;
- optional funding filter, default off;
- 1H pivot-high resistance clusters with `min_touches`;
- volume-at-price HVN-lite and VWAP confluence scoring;
- support target from pivot-low clusters below entry;
- rejection confirmation: tag resistance, close back below, upper wick, body, RSI, EMA extension;
- fail-closed risk gates: min/max stop pct, min RR, time stop, optional trail/BE;
- detailed `last_no_signal_reason`.

Integrated into:

- `backtest/run_portfolio.py`;
- risk mapping: `ARF2_RISK_MULT`, fallback `FLAT_RISK_MULT`;
- flat archetype/dynamic short symbol router;
- selector branch.

Tests:

- `tests/test_alt_resistance_fade_v2.py`

Focused validation:

```bash
source .venv/bin/activate
python -m py_compile strategies/alt_resistance_fade_v2.py backtest/run_portfolio.py
python -m pytest tests/test_alt_resistance_fade_v2.py tests/test_strategy_catalog.py -q
```

Result:

- `8 passed`.

Local runtime smoke:

```bash
BACKTEST_CACHE_ONLY=1 ARF2_RISK_MULT=1.0 ARF2_SYMBOL_ALLOWLIST=LINKUSDT,SUIUSDT \
python backtest/run_portfolio.py \
  --symbols LINKUSDT,SUIUSDT \
  --strategies alt_resistance_fade_v2 \
  --days 60 --end 2026-04-30 \
  --tag arf2_local_smoke_20260628 \
  --starting_equity 100 --risk_pct 0.005 --leverage 1 --max_positions 2 \
  --fee_bps 6 --slippage_bps 2 --entry-on-next-open
```

Result:

- runtime passed;
- 1 trade, net `-0.54`;
- this is not a strategy verdict, only a smoke check.

## New ARF2 server queue spec

New spec:

- `configs/autoresearch/arf2_structured_resistance_fade_20260628.json`

Added to:

- `configs/autoresearch/approved_specs.txt`;
- `configs/research_priority_24h_20260626.json`.

Spec properties:

- cache-only;
- 240d ending `2026-04-30`;
- next-open;
- fees/slippage `6/2` bps;
- 192 combos;
- max active server processes remains 1 via queue config.

Validation:

```bash
source .venv/bin/activate
python scripts/validate_sweep_configs.py --file configs/autoresearch/arf2_structured_resistance_fade_20260628.json --strict
python -m json.tool configs/research_priority_24h_20260626.json
```

Result:

- passed, no warnings.

Do not start ARF2 manually while another heavy research process is active on the 1GB VPS. Let the queue run it after current jobs, or manually run only when server is idle.

## Current crypto candidate map

### First serious canary candidate

ATT1 short-only / trendline touch:

- file: `strategies/alt_trendline_touch_v1.py`;
- best server revalidation:
  - 457 trades;
  - net `+37.35`;
  - PF `1.325`;
  - WR `58.9%`;
  - DD about `4.67–6.41` depending on summary/DD-doctor;
  - 2 red months;
  - max red streak 1;
  - short side much stronger than long side.

Current work:

- server package `package_att1_short_ars1_additivity_20260628` is running/queued;
- it tests whether ARS1 improves ATT1 or worsens monthly/DD;
- `RANGE_RISK_MULT=0.00` rows are ATT1-only controls.

### Diversifier candidate

SpikeFadeV3 LINK short-only:

- file: `strategies/spike_fade_v3.py`;
- best bounded result:
  - 360d;
  - 32 trades;
  - net `+5.10`;
  - PF `1.987`;
  - WR `59.4%`;
  - DD `1.27`;
  - 2 red months;
  - max red streak 1.

Interpretation:

- good low-frequency diversifier;
- not a portfolio engine by itself.

### Watch candidate

IVB1 short / impulse-volume breakout:

- file: `strategies/impulse_volume_breakout_v1.py`;
- best known package-ish result:
  - 289–312 trades depending on run/sample;
  - net about `+15–16`;
  - PF about `1.25`;
  - WR about `55%`;
  - DD `8.45–8.99`.

Interpretation:

- has edge but DD gate still fails;
- needs DD repair, side/symbol gating, and maker/fill-risk work before live risk.

### Range/pila status

Legacy `range` wrapper is not to be unfrozen:

- 180d replay: 280 trades, net `-18.60`, PF `0.61`, DD `20.54`, 5 red months in a row.

ARS1:

- currently under server additivity test with ATT1;
- do not assume it helps until final package result.

ARF2:

- new research-only attempt to rebuild the short resistance-fade sleeve from better level logic.

### Current no-go / rewrite later

- Breakdown V1: fresh sweep failed badly; keep disabled until entry rewrite.
- ASB1 current implementation: mass-failed; preserve long support-bounce idea for later rewrite, not live.
- Elder current standalone versions: failed as engines; likely future use as filter/booster, not core sleeve.
- PFS1 solo bounded: 0 trades in current config; needs event/funding data redesign.

## Immediate next actions

1. Commit and push the current ARF2 + web runner changes.
2. Deploy to server by git pull only if server worktree is clean enough; otherwise use tar/scp targeted deploy as previous sessions did.
3. Do not restart live bot for ARF2; only research queue files need server update.
4. Check current server research:

```bash
cd /root/by-bot
pgrep -fal 'run_strategy_autoresearch|run_portfolio|smart_pump'
tail -n 80 logs/research_priority_24h/package_att1_short_ars1_additivity_20260628_*.log
```

5. When `package_att1_short_ars1_additivity` finishes:
   - compare best rows against ATT1-only controls;
   - if ARS1 does not improve DD/monthly stability, do not include it in first canary;
   - first controlled crypto package should likely start with ATT1 short-only + SpikeFadeV3 LINK short-only, and add ARF2 only if the new sweep passes.

## First controlled portfolio target

Not live yet, but the intended construction is:

- short engine: ATT1 short-only;
- short diversifier: SpikeFadeV3 LINK short-only;
- range/chop candidate: ARF2 if sweep passes; otherwise keep range in research;
- long candidate: none promoted now; ASB1/current long bounce failed, ATT1 long can be preserved for bull regime but not first bear/chop canary.

Controlled unfreeze gate:

- execution replay passes;
- monthly red months <= 3, red streak <= 2;
- DD within gate;
- live pause/risk env respected;
- shadow first, then tiny canary with rollback.
