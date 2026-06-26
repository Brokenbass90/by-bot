# CODEX HANDOFF — 2026-06-26

Branch: `codex/dynamic-symbol-filters`

Workspace: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28`

Server: `root@64.226.73.119`, live path `/root/by-bot`

## User context

The owner is frustrated after months of weak progress. Main demand: stop hand-waving, rebuild a real crypto portfolio, preserve classic trading ideas, prove everything through reproducible server data, and keep research running when the Codex chat is closed.

Communication style requested: direct, factual, pragmatic, no motivational fluff.

## Current live status

As of 2026-06-26 ~12:10 UTC:

- `bybot.service` is active.
- Live bot MainPID was `578110`.
- No live restart was performed during this session.
- Strategy research queue is running on server.
- Active research process: `hzbo1_24h_bounded_v1`.
- Research cron installed:

```cron
*/10 * * * * cd /root/by-bot && .venv/bin/python3 scripts/run_nightly_research_queue.py --config configs/research_priority_24h_20260626.json --quiet >> logs/research_priority_24h/cron.log 2>&1
```

This cron is bounded: one active research process max via `configs/research_priority_24h_20260626.json`.

## Commits pushed this session

1. `d67665a repair candidate sleeve guards and add 24h crypto research queue`

Changed:

- `strategies/impulse_volume_breakout_v1.py`
- `strategies/pump_fade_smart_v1.py`
- `strategies/alt_inplay_breakdown_v1.py`
- `strategies/spike_fade_v3.py`
- `strategies/elder_triple_screen_v2.py`
- `tests/test_classic_strategy_geometry_guards.py`
- `configs/autoresearch/*_24h_bounded_v1.json`
- `configs/research_priority_24h_20260626.json`
- `reports/CRYPTO_PORTFOLIO_RECOVERY_PLAN_2026_06_26.md`

2. `e7ca451 make priority crypto research queue safe for live VPS`

Changed:

- added `configs/autoresearch/pfs1_solo_24h_bounded_v1.json`
- replaced heavy PFS1 package task with lightweight solo task
- updated approved specs and recovery plan

3. `a8c3243 document strategy logic and wire spike fade into portfolio runner`

Changed:

- `backtest/run_portfolio.py`: supports `spike_fade_v3`
- `tests/test_spike_fade_v3.py`: regression guard that portfolio runner supports `spike_fade_v3`
- `reports/STRATEGY_LOGIC_HUMAN_2026_06_26.md`
- `CODEX_HANDOFF_2026_06_26.md`

Local full suite after this commit: `440 passed`.

4. `c8a2e15 queue att1 density top-pocket revalidation`

Changed:

- added `configs/autoresearch/att1_density_top_revalidate_20260626.json`
- appended `att1_density_top_revalidate` to `configs/research_priority_24h_20260626.json`

Purpose: preserve and re-check the old May-25 ATT1 density pocket that showed about `+38%`, PF `~1.38`, WR `~59.6%`, DD `~4%`, but under current code and stricter `--entry-on-next-open` execution. This is not a live promotion; it is revalidation of a previously strong sweep.

## Server deploys performed

No `git pull` on server because `/root/by-bot` is dirty/old.

Patch deploys used tar/scp:

- `/tmp/codex_d67665a_crypto_research.tar`
- `/tmp/codex_prev_strategy_fixes_20260626.tar`
- `/tmp/codex_e7ca451_priority_queue_safe.tar`
- `/tmp/codex_a8c3243_spike_docs.tar`

Backups on server:

- `/root/by-bot_backups/d67665a_20260626/`
- `/root/by-bot_backups/prev_strategy_fixes_20260626/`
- `/root/by-bot_backups/e7ca451_20260626/`
- `/root/by-bot_backups/a8c3243_20260626/`
- `/root/by-bot_backups/c8a2e15_20260626/`

Server tests after deploy:

```bash
.venv/bin/python3 -m pytest -q tests/test_classic_strategy_geometry_guards.py tests/test_inplay_retest_v3.py tests/test_inplay_breakout_wrapper.py
```

Result: `24 passed`.

Local full suite before final docs/spike integration:

```bash
pytest -q
```

Result before `a8c3243`: `439 passed`.

Local full suite after `a8c3243`: `440 passed`.

Server test after `a8c3243` deploy:

```bash
.venv/bin/python3 -m pytest -q tests/test_spike_fade_v3.py
```

Result: `6 passed`.

Server validation after `c8a2e15` deploy:

```bash
.venv/bin/python3 scripts/validate_sweep_configs.py --file configs/autoresearch/att1_density_top_revalidate_20260626.json
```

Result: passed, no warnings.

## Research queue status and results

Priority queue file: `configs/research_priority_24h_20260626.json`

Logs: `/root/by-bot/logs/research_priority_24h/`

Status: `/root/by-bot/runtime/research_priority_24h/status.json`

### IVB1

Spec: `configs/autoresearch/ivb1_short_next_open_recheck_v1.json`

Result: WATCH, not live.

Best:

- `net=15.23`
- PF `1.250`
- WR `0.547`
- DD `8.4586`
- failed only because `dd>8.0`

Interpretation: first real crypto candidate. Needs DD-cut / lower risk / maker-fill risk / monthly.

### Breakdown V1

Spec: `configs/autoresearch/breakdown_recent_bear_window_v2_entry_quality.json`

Result: CUT FOR NOW.

Best:

- `net=-8.47`
- PF `0.580`
- WR `0.404`
- DD `8.7298`

Interpretation: current Breakdown V1 should not be unfrozen. Needs entry rewrite, not grid.

### PFS1

Original heavy package `package_pfs1_pump_fade_v1` was manually stopped.

Reason: on 1GB live VPS it used ~506MB RSS next to live bot and left ~53MB available. That is OOM risk.

Replacement: `pfs1_solo_24h_bounded_v1`

Result:

- 16/16 failed
- 0 trades

Interpretation: current solo config too strict or PFS1 needs real historical funding-event mode. Not live.

### SpikeFadeV3

Spec: `configs/autoresearch/spike_fade_v3_24h_bounded_v1.json`

Previous result: invalid run, not a strategy verdict.

Cause:

- `backtest/run_portfolio.py` did not support `spike_fade_v3`.
- All rows failed with `Unsupported strategy 'spike_fade_v3'`.

Fixed in `a8c3243` and deployed to server:

- `backtest/run_portfolio.py` now supports `spike_fade_v3`;
- server `tests/test_spike_fade_v3.py` passes;
- old invalid spike log was moved under `logs/research_priority_24h/invalid/`;
- `spike_fade_v3_bounded` was removed from `runtime/research_priority_24h/task_state.json`.

Next: let cron rerun it automatically after current HZBO process releases the single research slot.

### HZBO1

Spec: `configs/autoresearch/hzbo1_24h_bounded_v1.json`

At handoff time:

- active process: `hzbo1_24h_bounded_v1`, around row r007/32
- early rows weak: negative net, PF `<1`, DD high.

Need wait for completion before final verdict.

### ETS2 / InPlay Retest V3

Still deferred behind active queue.

Need ensure Spike rerun after integration fix and HZBO completion.

### ATT1 density top-pocket revalidation

Spec: `configs/autoresearch/att1_density_top_revalidate_20260626.json`

Queued after `inplay_retest_v3_bounded`.

Why: old local sweep `att1_density_v3_more_pivots_v1` had strong top rows:

- net about `+38%`
- PF about `1.38`
- WR about `59.6%`
- DD about `4%`
- around `406` trades

Top pocket params:

- `ATT1_PIVOT_LEFT=2`
- `ATT1_PIVOT_RIGHT=3`
- `ATT1_MIN_PIVOTS=2/3`
- `ATT1_MAX_PIVOT_AGE=16/20/24`
- `ATT1_MIN_R2=0.55/0.65`
- `ATT1_TOUCH_ATR=0.5`
- `ATT1_RSI_LONG_MAX=52`

This revalidation adds `--entry-on-next-open`; expect lower results than old sweep. If it survives, next step is monthly/WF and live/backtest parity.

## What was fixed in candidate strategies

### IVB1

- added `IVB1_MIN_RR`
- added `IVB1_MAX_ENTRY_DIST_ATR`
- risk geometry now uses current `atr_5m`
- `_armed` state resets on runtime config signature change

### PFS1

- added `PFS1_MIN_STOP_PCT`, `PFS1_MAX_STOP_PCT`
- funding fetch now passes `ts_ms` if store supports it
- same-bar dedupe uses actual signal candle timestamp
- selector can `reset_all()`

### Breakdown V1

- added `BREAKDOWN_MIN_RR`
- added `BREAKDOWN_MIN_STOP_PCT`, `BREAKDOWN_MAX_STOP_PCT`
- added trailing fields to signal

### SpikeFadeV3

- SL geometry uses entry ATR, not structure ATR
- `run_portfolio.py` integration is deployed and tested on server

### ETS2

- added `ETS2_MIN_RR`
- added `ETS2_MIN_STOP_PCT`, `ETS2_MAX_STOP_PCT`
- added `ETS2_MAX_ENTRY_DIST_ATR`
- actual RR checked after structural stop widening

## Important docs

- `reports/CRYPTO_PORTFOLIO_RECOVERY_PLAN_2026_06_26.md`
- `reports/STRATEGY_LOGIC_HUMAN_2026_06_26.md`
- `CODEX_HANDOFF_2026_06_26.md`

## DeepSeek/Claude notes to preserve

The attached DeepSeek text argues for:

- regime detector;
- portfolio risk manager;
- funding/liquidation/order-book structural edges;
- using DeepSeek/Claude as accelerated reviewers/spec writers;
- not relying on a single magic strategy.

Codex interpretation:

- valid direction, but do not start 5 new strategies before proving current queue;
- next infra priority after queue: strategy-specific regime affinity + portfolio replay;
- use Claude for logic review and visual-level sanity checks, not for live promotion authority.

## Immediate next steps for next Codex

1. Check current research status:

```bash
cd /root/by-bot
.venv/bin/python3 -c "import pathlib; print(pathlib.Path('runtime/research_priority_24h/status.json').read_text())"
tail -80 logs/research_priority_24h/cron.log
```

2. Wait for HZBO to finish. Current early HZBO rows are weak, but final verdict requires full 32/32.

3. Confirm cron launches SpikeFadeV3 after HZBO. It should, because the invalid spike log was moved and task state was cleared. If task_state somehow blocks it, clear only `spike_fade_v3_bounded` from:

```bash
/root/by-bot/runtime/research_priority_24h/task_state.json
```

Then:

```bash
cd /root/by-bot
.venv/bin/python3 scripts/run_nightly_research_queue.py --config configs/research_priority_24h_20260626.json --quiet
```

4. Return to owner with updated PASS/WATCH/CUT:

- IVB1 = WATCH
- Breakdown V1 = CUT FOR NOW
- PFS1 solo = CUT/RESEARCH, 0 trades
- Spike = rerun pending after integration fix
- HZBO = pending/likely weak early
- ETS2 = pending
- InPlay Retest V3 = pending
- ATT1 density top-pocket = queued revalidation of old strong sweep, not live

## When can crypto unfreeze?

Not immediately.

Earliest path:

- IVB1 monthly/DD-control replay today/tomorrow;
- if DD can be reduced and monthly is not concentrated, IVB1 can enter shadow;
- if shadow clean, canary after that.

Do not unfreeze Breakdown V1 or PFS1 from current results.

## Alpaca

Not rechecked in this turn. Previous plan remains: Alpaca is likely the first real-money candidate, but only after post-2026-06-26 market-close execution review: broker stops, fills, ownership, PnL accounting, no duplicate orders. If clean, `$500 @ 1.0x` canary is reasonable. Do not answer “yes, fund now” without doing that check.
