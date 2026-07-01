# Morning status — 2026-07-01

## Live crypto

Server proof-of-life at `2026-07-01T05:33:22Z`:

- `STATUS: ALIVE`
- `regime=bear_chop`
- `dry_run=False`
- `open_trades=0`
- market feed OK, Bybit messages growing
- `hard_block=False`, `safe_mode=False`
- active live-risk sleeve: `att1` / trendline touch, `risk_mult=0.10`
- shadow / zero-risk sleeves: `range`, `flat`, `ivb1`, `midterm`, `bounce1`

Interpretation: the bot is not globally frozen. It is live with only ATT1
short-only risk. No trades happened because ATT1 has not found a valid short
trendline setup.

## Server safety action

A stale `ars1_side_regime_repair_20260627` research run was active on the 1GB
live VPS:

- child process: `backtest/run_portfolio.py ... alt_range_scalp_v1 ... r107`
- memory: about `380MB`
- CPU: about `88%`
- available RAM before stop: about `155MB`

The research process was stopped. Live bot and the liquidation collector were
not touched.

Available RAM after stop: about `503MB`.

Rule: heavy sweeps must not run next to live on the 1GB VPS. Use local machine or
a separate research host.

## Overnight local research result

Local overnight log:

`logs/manual_research/local_overnight_20260630_20260630_194550.log`

Completed successfully.

### Market survey

`scripts/market_survey.py` scanned 60 symbols:

- `38` LEVELS / mixed-structure symbols
- `16` RANGE / BOUNCE symbols
- `6` HIGH_VOL symbols

This is a scout / universe map, not an entry signal.

### InPlay V4 OOS smoke

Universe `ADAUSDT,DOGEUSDT,SUIUSDT`, short-only:

- best shown local variant: `195` trades, `+1.38R`, PF `1.039`, WR `55.9%`, DD `7.55R`

Universe `LINKUSDT,SOLUSDT,ADAUSDT`, short-only:

- all tested variants negative, PF roughly `0.78-0.87`, DD roughly `11.5-12.4R`

Verdict: InPlay V4 is a useful research skeleton, but not a live candidate yet.
It needs helper-layer wiring (`retest_quality`, `range_filter`, optional
`elder_filter`) and symbol-specific OOS validation.

### SpikeFadeV3 LINK short-only

OOS-style checks:

- 90d: `2` trades, `+0.86R`, PF `inf`, DD `0.018R` — too few trades
- 240d: `16` trades, `+5.02R`, PF `3.764`, WR `75%`, DD `0.55R`
- 360d: `29` trades, `+5.21R`, PF `2.107`, WR `62.1%`, DD `1.27R`

Verdict: best current crypto directional add-on candidate, but low frequency.
Next step is server replay / gate, then tiny canary only with breaker + expiry.

## Horizontal levels

Current live risk does **not** trade horizontal/range/bounce/breakout money.
Only ATT1 short trendline has risk.

Horizontal logic exists in the new foundation:

- `bot/range_filter.py`
- `bot/retest_quality.py`
- `bot/breakout_confirm.py`
- `bot/pump_exhaustion.py`
- `bot/elder_filter.py`
- `bot/market_context.py`

But those helpers are not yet wired into live sleeves with proven OOS. Next
engineering task: phased wiring + OOS, not blind unfreeze.

## Alpaca

Alpaca remains the nearest real-money path, but the current Telegram examples
were paper / dry-run telemetry, not live proof.

Owner action:

1. Create/fund live Alpaca account with about `$500`.
2. Generate live API keys.
3. Do not paste keys into chat.
4. Put keys into server-only `configs/alpaca_live_v38.env`.
5. First run live account with `ALPACA_SEND_ORDERS=0` dry-run.
6. Enable send-orders only after owner OK during market hours.

## Why old big backtests became non-combat evidence

The old `+89% / +120%` class numbers are not reliable current baseline because
the validation contract changed:

1. closed-candle / forming-candle bugs were found and fixed;
2. next-open execution replaced same-bar assumptions in more places;
3. fees/slippage and maker/taker sensitivity became explicit;
4. strategy-only runs were compared against full stack caps / wrappers;
5. OOS / monthly stability became required instead of selecting a pretty peak;
6. stale cache/date/symbol mixes were normalized.

This does not mean the ideas are dead. It means old numbers were not sufficient
evidence for live risk.

## Can current tests also be wrong?

Yes. The control is not blind trust in the new tests; it is a validation ladder:

1. unit tests for indicators and helper contracts;
2. closed-candle tests and live/backtest parity tests;
3. next-open execution and explicit costs;
4. OOS / WF, monthly stability, red-streak and concentration checks;
5. stack comparison: bare strategy vs live wrapper;
6. shadow/live signal replay with the same data;
7. tiny canary with breaker, expiry and broker/journal reconciliation.

Candidates that fail this ladder stay research-only.

## Immediate next actions

1. Keep ATT1 short-only canary live and waiting.
2. Prepare SpikeFadeV3 LINK short-only for server gate / tiny canary.
3. Wire horizontal helper layers into ARF2/ASB2/ACB1/InPlay V4 in research only.
4. Move heavy sweeps off the live VPS.
5. Start Alpaca `$500` live-account dry-run once the owner funds the account.
