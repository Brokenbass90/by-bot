# Codex handoff — 2026-06-04

## Read this first

Primary goal: turn the existing crypto, Alpaca, and cross-exchange research into
small, protected, observable live sleeves without promoting weak strategies or
confusing open shadow PnL with earned return.

Repository:

- path: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28`
- branch: `codex/dynamic-symbol-filters`
- server: `/root/by-bot`
- never commit `configs/web_config.json` or credential/env files
- the worktree contains a large old dirty/untracked tail; always commit scoped

## Current live crypto state

Checked on 2026-06-04 around 18:15 UTC:

- `bybot.service`: active
- heartbeat: fresh
- `trade_on=1`, `dry_run=0`, `open_trades=0`
- regime: `bear_trend`, confidence about `0.57`
- router: healthy
- allocator: intentionally disabled by the strict canary overlay, not degraded
- strict caps remain active

Recent crypto stop-losses were real strategy losses, not missing exchange
protection. Normal algorithmic entries had exchange-side SL/TP. The earlier
restored/bootstrap BTC position with missing TP was a separate bug fixed before
this handoff.

Live sample is still too small:

- breakdown: 8 closes, WR 25%, PF about 0.26
- range: 1 loss
- ATT1: 1 loss

Do not loosen filters based only on this sample. Use exact-cache package replay,
then zero-risk shadow, then capped canary.

## Proven package and IVB1 decision

Exact-cache dataset:

`./.cache/validated/crypto_static_v1_20260425`

Five-slot baseline:

- net `+65.89%`
- PF `1.462`
- DD `7.49%`
- 486 trades
- 3 negative months

Five-slot candidate with IVB1:

- net `+74.51%`
- PF `1.528`
- DD `5.52%`
- 493 trades
- 1 negative month

Strict-three baseline:

- net `+59.31%`
- PF `1.409`
- DD `10.08%`
- 4 negative months

Strict-three IVB1:

- net `+64.90%`
- PF `1.452`
- DD `5.22%`
- 2 negative months

Decision:

- IVB1 is deployed as telemetry-only shadow.
- Effective overlay now has `ENABLE_IVB1_TRADING=1` and
  `IVB1_RISK_MULT=0.00`.
- The bot log confirms `ivb1=True`.
- The shadow branch returns before any order-submission code.
- Do not add capital risk until shadow signals are observed and reviewed.

Important bug fixed: `.env` enabled IVB1, but
`configs/approved_strategy_params.env` loaded later with `override=True` and
disabled it. The approved overlay now preserves zero-risk shadow.

## ATT1 rounding

The claim that `att1_skip_rounding` is always a bug was not proven. The rounding
guard is a safety boundary. Diagnostics were expanded to record raw and rounded
SL/TP, entry, and runner mode. Wait for the next explainable event before
changing execution semantics.

## Strategy research queue

### SC1 classic scalper

`strategies/scalper_classic_v1.py` was repaired for research:

- valid `TradeSignal.strategy`
- normalized `long` / `short` sides
- TP1/TP2 fractions, breakeven trigger, and time stop
- wired into the backtest runner only, not live

Exact-cache package probe results:

| Mode | Net | PF | DD | Trades | Negative months | Decision |
|---|---:|---:|---:|---:|---:|---|
| bounce | +52.28% | 1.273 | 13.72% | 950 | 5 | reject |
| sweep | -99.99% | 0.525 | 99.99% | 10,075 | 13 | reject |
| breakout | +34.32% | 1.152 | 17.66% | 1,128 | 5 | reject |

Do not run the old 729-combo SC1 sweeps. SC1 does not improve the package in its
current form.

### Elder

Prepared and validated:

`configs/autoresearch/package_elder_modes_exact_probe_v1.json`

It tests exactly four tide modes:

- EMA slope on 4h
- EMA slope on 1h
- relaxed MACD histogram on 4h
- relaxed MACD histogram on 1h

It runs in detached screen:

`elder_exact_probe_20260604`

First completed mode already failed:

- EMA slope on 4h: net `-0.16%`, PF `1.00`, DD `36.86%`, 2,697 trades,
  6 negative months

Inspect:

```bash
screen -ls
tail -50 logs/elder_exact_probe_20260604.log
find backtest_runs -maxdepth 1 -type d -name 'autoresearch_*elder_modes_exact_probe_v1'
```

If no mode beats PF `1.462`, DD `7.5%`, and net `65.9%`, reject Elder in this
form. If a mode passes, give only that mode a bounded parameter sweep and then
bear/bull split stress.

### Weekly research cadence

Target: research 2–3 candidates per week, not promote 2–3 live sleeves per week.

Each candidate must pass:

1. exact-cache package additivity
2. OOS/regime stress
3. zero-risk shadow
4. capped canary
5. full live only after enough closed trades

Next candidates after Elder should come from pump/dump/inplay families, but only
small mode probes first.

## Optional strategy hooks

Do not enable volume confirmation, dynamic loss-streak cooldown, or funding
filters blindly. They are behavior changes and can reduce frequency or conceal
the actual mismatch. Add them only as opt-in sweep dimensions and promote only
if the full package improves.

## Alpaca

v38 evidence:

- 24-month backtest: `+58.15%`
- PF `6.62`
- WR `80%`
- max monthly DD about `-3.86%`
- one negative active month

Paper mechanics passed:

- broker-side stop protection was observed
- software trailing uses high-water mark
- QCOM trail closed after a peak/giveback
- re-entry block worked
- no cleanup conflict observed

However, the current monthly paper gate now reports
`filtered_to_zero_candidates`: all current monthly picks are re-entry blocked,
while the shared paper account also contains intraday-managed positions. Do not
fund live today.

Next Alpaca action:

1. create a monthly-v38-only live credentials/profile
2. run read-only preflight
3. produce a non-empty protected order plan capped at `$500`
4. require explicit confirmation `MONTHLY_V38_LIVE`

This does not require waiting another month, but it does require account/sleeve
separation and a non-empty plan.

Other versions:

- v39 files:
  - `strategies/alpaca_dynamic_v3_event.py`
  - `scripts/alpaca_v3_event_backtest.py`
  - `scripts/alpaca_v39_ohlc_trailing_backtest.py`
  - `configs/alpaca_v39_event_best_research.env`
- v39 is promising (`+70.37%/24m`, PF `1.85`) but failed bear-2022
  (`-23.47%`, PF `0.415`). It needs defensive/cash logic and regime stress;
  estimate 2–4 weeks of research, not live.
- v40 research files:
  - `strategies/alpaca_dynamic_v4_event.py`
  - `scripts/alpaca_v4_event_backtest.py`
  - currently rejected
- intraday v1 files:
  - `scripts/equities_alpaca_intraday_bridge.py`
  - `scripts/run_equities_alpaca_intraday_dynamic_v1.sh`
  - `configs/alpaca_intraday_dynamic_v1.env`
  - current result is negative and rejected

## Cross-exchange arbitrage

Current honest evidence:

- `runtime/arb_roi_estimate.json`: `insufficient_closed_cycles`
- closed eligible cycles: `0`
- required before projection: at least `10`
- current dry-run ready count: `0`

Read-only account status works:

- Bybit: about `$122.60`
- Binance: about `$11.70`
- Bitget: `$0`
- MEXC: no keys

Dry-run is blocked only by balances. It needs at least `$20` on each required
leg. This is not permission to fund `$1000` live. First collect closed shadow
cycles, then use a tiny live canary with caps.

Do not implement automatic withdrawals/transfers initially. Pre-fund exchanges
manually. Automated inventory transfer is a later high-risk phase after order
execution, reconciliation, fee accounting, and emergency-stop behavior are
proven.

## AI and journals

The AI full context already includes:

- setup cards
- blocker report
- closed trade history/per-sleeve stats
- cross-exchange raw/validated/shadow data
- honest arb ROI evidence
- account status and dry-run plans

`post_trade_ai_review.py` can generate read-only trade reviews. AI may propose
settings, but must not auto-change live risk/configs or submit orders.

## Validation and known limitations

Passed:

- Python compilation for edited Python files
- manual IVB1 shadow guard checks
- manual SC1 signal-contract check
- strict sweep config validation
- `git diff --check`
- server heartbeat/control-plane check

Local `pytest` is unavailable in both system Python and `.venv`; do not claim
pytest passed.

## Scoped files for the next commit

Only stage these:

- `backtest/run_portfolio.py`
- `configs/approved_strategy_params.env`
- `smart_pump_reversal_bot.py`
- `strategies/scalper_classic_v1.py`
- `tests/test_ivb1_shadow_guard.py`
- `tests/test_att1_rounding_diagnostics.py`
- `tests/test_scalper_classic_contract.py`
- `configs/autoresearch/package_sc1_modes_exact_probe_v1.json`
- `configs/autoresearch/package_elder_modes_exact_probe_v1.json`
- `docs/CODEX_HANDOFF_2026_06_04_NEXT_CHAT.md`

Never stage `configs/web_config.json`, logs, reports, caches, runtime files, or
the unrelated untracked Claude/document tail.

## First actions in the next chat

1. Read this file.
2. Inspect the Elder exact probe result.
3. Check IVB1 shadow telemetry and recent crypto closes.
4. Build the isolated Alpaca monthly-v38 live preflight/profile.
5. Recheck arb closed-cycle count and balances; do not project ROI before the
   evidence gate.
