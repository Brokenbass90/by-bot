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

5. `bae02c1 make priority queue resource-safe and add arf1 scanner allowlist probe`

Changed:

- added `configs/autoresearch/spike_fade_v3_smoke_20260626.json`
- added `configs/autoresearch/arf1_scanner_allowlist_probe_20260626.json`
- changed priority queue so `spike_fade_v3_bounded` uses the resource-safe smoke spec instead of the heavy 128-combo spec
- appended `arf1_scanner_allowlist_probe` to the queue

Reason:

- the full `spike_fade_v3_24h_bounded_v1` rerun no longer failed as unsupported, but rows r001-r005 timed out at 900s each on the 1GB live VPS;
- the heavy Spike run was manually stopped on server to avoid burning the queue for 24h+;
- the owner/AI operator noticed scanner flat-short cards on SOL/ATOM/BTC/XRP while live ARF1 allowlist is narrow. The ARF1 probe tests expanded scanner-driven allowlist in backtest only; no live reload.

6. `347f7fb approve resource-safe priority research specs`

Changed:

- appended to `configs/autoresearch/approved_specs.txt`:
  - `spike_fade_v3_smoke_20260626.json`
  - `att1_density_top_revalidate_20260626.json`
  - `arf1_scanner_allowlist_probe_20260626.json`

Reason: `run_nightly_research_queue.py` only auto-runs approved specs. New specs can otherwise be proposed/deferred and consume a queue slot without executing.

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
- `/root/by-bot_backups/bae02c1_20260626/`

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

Server validation after `bae02c1` deploy:

```bash
.venv/bin/python3 scripts/validate_sweep_configs.py --file configs/autoresearch/spike_fade_v3_smoke_20260626.json
.venv/bin/python3 scripts/validate_sweep_configs.py --file configs/autoresearch/arf1_scanner_allowlist_probe_20260626.json
.venv/bin/python3 -m json.tool configs/research_priority_24h_20260626.json
```

Results: both specs passed, no warnings; queue JSON valid.

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

Final result:

- 32/32 failed.
- Best: `hzbo1_24h_bounded_v1_r003`
- net `-3.81`
- PF `0.919`
- WR `0.342`
- DD `12.4078`

Verdict: CUT/REWRITE FOR NOW. Current HZBO1 horizontal breakout/failure implementation is not a live candidate.

### ETS2 / InPlay Retest V3

As of 2026-06-26 ~15:35 UTC, ETS2 is active:

- active spec: `configs/autoresearch/ets2_canonical_24h_bounded_v1.json`
- row r001 already failed badly: net `-58.85`, PF `0.709`, DD `60.200`
- do not judge until full 64 rows finish, but early signal is weak.

InPlay Retest V3 still deferred behind ETS2.

### SpikeFadeV3

Heavy spec:

- `configs/autoresearch/spike_fade_v3_24h_bounded_v1.json`
- rerun reached rows r001-r005 and all timed out at 900s.
- active parent/child were killed manually on server:
  - old parent: `632798`
  - old child: `634884`

Replacement:

- `configs/autoresearch/spike_fade_v3_smoke_20260626.json`
- 4 combinations, 4 symbols, 120 days, next-open, timeout 600s
- approved and queued under the existing task name `spike_fade_v3_bounded`.

Need after ETS2: verify queue launches smoke, not old heavy spec.

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

### ARF1 scanner allowlist probe

Spec: `configs/autoresearch/arf1_scanner_allowlist_probe_20260626.json`

Queued after ATT1 top-pocket.

Purpose: test the operator/AI claim that flat/ARF1 is silent partly because scanner high-score symbols are not in the live ARF1 allowlist. The probe compares:

- current-ish core: `ADA,LINK,LTC,DOT,SUI`
- expanded scanner-driven set: `ADA,LINK,LTC,DOT,SUI,SOL,ATOM,BTC,XRP`

Execution: 180d, next-open, 16 combinations, research-only. Do not reload live config based on scanner cards before this result.

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

## 2026-06-27 pre-sleep update — owner-context + overnight queue

User pushed for a richer bot that does not trade a flat mathematical shadow of
the manual setup. Codex added a read-only owner-style setup context layer:

- `bot/owner_setup_context.py`
- `scripts/owner_setup_context_report.py`
- `tests/test_owner_setup_context.py`

What it checks:

- current in-play volume inflow;
- strong 1H level;
- entry distance to level;
- room to the next level;
- RR proxy;
- explicit reject reasons such as `volume:*`, `level_missing`,
  `entry_far_from_level`, `target_level_missing`, `rr_proxy_low`.

Validation:

```bash
.venv/bin/python -m pytest tests/test_owner_setup_context.py tests/test_inplay_volume_universe.py -q
# 7 passed
```

The first local diagnostic report:

- `reports/OWNER_SETUP_CONTEXT_latest.md`
- current local cache had 0/8 candidates on BTC/ETH/SOL/LINK, correctly rejecting
  non-inplay/far-from-level setups.

This is not wired into live risk. Next implementation step is A/B research:

- old level-first InPlay/ARF1/ATT1;
- new volume-first + level-quality owner context gate.

## Overnight queue extension

The server priority queue was extended with three bounded research-only jobs.
After seeing the current InPlay run still active, the queue was reordered so
the new P0 research jobs run immediately after InPlay; ATT1/ARF1 remain queued
after them.

1. `sloped_resistance_choch_bounded_20260627.json`
   - short-only repeated sloped/horizontal resistance + rejection + 5m CHoCH;
   - tests the owner’s “short breakdown of sloped levels” logic.
2. `ivb1_short_wider_bounded_20260627.json`
   - expands the only currently positive crypto price-action candidate, IVB1
     short, to a wider universe with stricter entry-distance guards.
3. `funding_reversion_short_smoke_20260627.json`
   - small structural smoke: positive funding → short reversion;
   - caveat: mocked funding, validates price/exit filters only.

All three:

- cache-only;
- one-at-a-time through `configs/research_priority_24h_20260626.json`;
- approved in `configs/autoresearch/approved_specs.txt`;
- passed JSON load, strict sweep validation, and `ResearchGate.can_run=True`.

Full priority queue order now:

1. `ivb1_short_next_open_recheck`
2. `breakdown_bear_entry_quality`
3. `pfs1_solo_bounded`
4. `spike_fade_v3_bounded`
5. `hzbo1_bounded`
6. `ets2_canonical_bounded`
7. `inplay_retest_v3_bounded`
8. `sloped_resistance_choch_bounded`
9. `ivb1_short_wider_bounded`
10. `funding_reversion_short_smoke`
11. `att1_density_top_revalidate`
12. `arf1_scanner_allowlist_probe`

At 2026-06-26 ~22:41 UTC server was still running:

- `inplay_retest_v3_24h_bounded_v1`, row `r036/64`;
- live bot active;
- research guard status OK.
- server owner-context diagnostic completed: `candidates_ok=2/16`.

## Morning checks

1. Check current research status:

```bash
cd /root/by-bot
.venv/bin/python3 -c "import pathlib; print(pathlib.Path('runtime/research_priority_24h/status.json').read_text())"
tail -80 logs/research_priority_24h/cron.log
tail -120 logs/research_priority_24h/*.log
```

2. Check which row is active:

```bash
pgrep -fal "run_strategy_autoresearch|run_portfolio.py"
cat runtime/research_guard/status.json
```

3. If queue is blocked because no active process but a task is stuck in `launched`,
run once:

```bash
cd /root/by-bot
.venv/bin/python3 scripts/run_nightly_research_queue.py --config configs/research_priority_24h_20260626.json
```

Do not start a second heavy runner manually while another `run_portfolio.py` is active.

4. If task_state somehow blocks a completed task, clear only that single task from:

```bash
/root/by-bot/runtime/research_priority_24h/task_state.json
```

Then:

```bash
cd /root/by-bot
.venv/bin/python3 scripts/run_nightly_research_queue.py --config configs/research_priority_24h_20260626.json --quiet
```

5. Return to owner with updated PASS/WATCH/CUT:

- IVB1 = WATCH
- Breakdown V1 = CUT FOR NOW
- PFS1 solo = CUT/RESEARCH, 0 trades
- Spike = rerun pending after integration fix
- HZBO = CUT/REWRITE after 32/32 fail
- ETS2 = active, early weak
- InPlay Retest V3 = pending
- ATT1 density top-pocket = queued revalidation of old strong sweep, not live
- ARF1 scanner allowlist probe = queued, tests whether live flat silence is allowlist/universe issue
- SRC1 sloped resistance CHoCH = queued after ARF1; this directly tests owner’s
  sloped-level short-breakdown hypothesis
- IVB1 short wider = queued after SRC1; expands the only current positive crypto
  candidate
- Funding short smoke = queued last; structural research only, not promotion data

## When can crypto unfreeze?

Not immediately.

Earliest path:

- IVB1 monthly/DD-control replay today/tomorrow;
- if DD can be reduced and monthly is not concentrated, IVB1 can enter shadow;
- if shadow clean, canary after that.

Do not unfreeze Breakdown V1 or PFS1 from current results.

## Alpaca

Not rechecked in this turn. Previous plan remains: Alpaca is likely the first real-money candidate, but only after post-2026-06-26 market-close execution review: broker stops, fills, ownership, PnL accounting, no duplicate orders. If clean, `$500 @ 1.0x` canary is reasonable. Do not answer “yes, fund now” without doing that check.

## Morning update — 2026-06-27

Server queue did not stall overnight:

- live bot still active, no restart performed;
- InPlay bounded run completed;
- `sloped_resistance_choch_bounded` completed;
- `funding_reversion_short_smoke` completed;
- `ivb1_short_wider_bounded` started and was on the final rows around
  2026-06-27 04:50 UTC.

Current morning verdicts:

- `ivb1_short_next_open_recheck_v1`: still the best price-action candidate.
  Best row `r005`: net `+15.23`, PF `1.25`, WR `~54.7%`, DD `8.46`.
  Fails only the strict DD gate.
- `inplay_retest_v3_24h_bounded_v1`: best row `r059`: net about `+1.01`,
  PF `1.072`, DD `1.83`, 90 trades. Safer but edge is too thin.
- `sloped_resistance_choch_bounded`: only ~1 trade in the bounded smoke;
  current wrapper/conditions are too narrow or not connected to the real manual
  sloped-breakdown logic yet.
- `funding_reversion_short_smoke`: failed; useful only as structural smoke
  because funding was mocked.

New reusable DD tool:

- `scripts/drawdown_doctor_report.py`

It reads `backtest_runs/.../trades.csv` plus optional
`trade_forensics_report.py` JSONL and writes:

- max-DD window start/trough;
- worst contributors by symbol, side, reason, month, UTC hour;
- contributors inside the max-DD window;
- forensic verdict contribution;
- concrete next hypotheses.

Server reports already generated:

- `reports/trade_forensics/trade_forensics_20260627_050212_dd_doctor_ivb1_20260627.md`
- `reports/trade_forensics/trade_forensics_20260627_050204_dd_doctor_inplay_20260627.md`
- `reports/drawdown_doctor/drawdown_doctor_ivb1_20260627.md`
- `reports/drawdown_doctor/drawdown_doctor_inplay_20260627.md`

Key IVB1 DD facts:

- combined IVB1 forensic sample: 312 trades, net `+16.45`, PF `1.254`,
  WR `55.4%`;
- max DD `8.9956`, from 2025-04-08 to 2025-08-13, 82 trades;
- worst symbols overall: BTCUSDT `-1.86`, SOLUSDT roughly flat;
- best contributors: ADAUSDT `+6.50`, DOGEUSDT `+4.93`, ETHUSDT `+2.98`,
  LINKUSDT `+2.70`;
- inside max-DD window, worst contributors were SOL/LINK/DOGE;
- dominant DD patterns:
  - `stop_then_reversed`;
  - `gave_back_profit`;
  - winners often `tp_then_continued`.

Concrete IVB1 hypotheses:

1. symbol gating: test removing BTC and possibly SOL from IVB1 short;
2. stop geometry: test wider SL / delayed entry / stop behind structure;
3. exit management: test breakeven or trailing after MFE threshold;
4. runner: test wider TP2 or ATR trailing runner.

Key InPlay DD facts:

- best bounded row: 90 trades, net `+1.01`, PF `1.072`, WR `41.1%`;
- max DD `4.71`, from 2025-08-19 to 2026-02-10, 52 trades;
- longs net negative, shorts net positive;
- NEAR/SUI were main max-DD contributors;
- dominant pattern: many SLs, winners continue after TP.

Next automation step:

- make DD doctor a mandatory postprocess for every promoted/reviewed
  autoresearch candidate: ranked row → trades.csv → trade_forensics →
  drawdown_doctor → only then GO/WATCH/CUT.
