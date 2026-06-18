# Maker execution and strategy queue — 2026-06-18

## 1. Deployed execution change

Commit `af9fdba` is deployed to `/root/by-bot` and pushed to
`origin/codex/dynamic-symbol-filters`.

The `range` and `flat_resistance_fade` canaries now use a fail-closed
maker-first entry path:

1. submit a Bybit `PostOnly` limit order;
2. poll for fill for a bounded interval;
3. cancel on timeout and require terminal cancel confirmation;
4. read the current position and fresh market price;
5. cross the spread only when price and stop risk remain inside limits;
6. never cross an unfilled remainder after a partial maker fill;
7. recalculate risk after the actual fill and reduce-only close a position
   whose fill risk exceeds the configured post-fill limit.

An uncertain order state remains quarantined and cannot be replaced by a
second entry. The server-targeted tests passed (`25 passed`), the complete
local suite passed (`372 passed`).

## 2. Live state after restart

Checked at `2026-06-18 11:06 UTC`:

- service: active;
- Bybit authentication: OK;
- market feed: OK (`bybit_msgs=20380` after startup subscription batching);
- real positions: 0;
- `dry_run=False`, `disabled=False`, `hard_block=False`, `safe_mode=False`;
- regime: `bear_chop`;
- live risk: `flat_resistance_fade x0.30`, `range x0.25`;
- shadow / zero risk: ATT1 trendline touch, support bounce, breakdown,
  old IVB1, BTC/ETH midterm.

The bot is not mechanically frozen. A quiet interval means that the two
risk-bearing sleeves did not produce a valid setup.

## 3. Range evidence

Closed `range` trades since `2026-06-17 00:00 UTC`:

| direction | trades | wins | net PnL, USDT |
|---|---:|---:|---:|
| long from support | 11 | 3 | -0.7842 |
| short from resistance | 3 | 2 | +0.5301 |
| total | 14 | 5 | -0.2542 |

The previous market-entry path also expanded actual stop risk on several
fills: approximately `1.31x` to `2.38x` of planned risk. The maker-first and
post-fill checks address that execution defect. They do not prove that the
long signal itself has positive expectancy. Long and short results must stay
separate in subsequent evaluation.

No risk increase is justified by this sample. The next useful checkpoint is
the first 5-10 entries executed by the new path, including maker fill rate,
fallback rate, slippage, post-fill risk ratio, and PnL by direction.

At `2026-06-18 11:09 UTC`, `configs/range_short_only_canary.env` was applied
after three flat-account confirmations. The live process now has
`RANGE_ALLOW_LONG=0`, `RANGE_ALLOW_SHORT=1`, and `RANGE_RISK_MULT=0.25`.
This preserves the active short side while the losing long side is returned
to validation. The market feed was `OK` after subscription startup.

## 4. Strategy queue

The current validation order is:

1. Elder EMA50 canonical pullback — server autoresearch is running on a
   360-day window with 6 bps fees and 2 bps slippage.
2. InPlay retest v3 — horizontal pivot clusters plus sloped regression
   levels, with independent long and short switches.
3. Breakdown retest v3 — short retest of broken support, evaluated as a
   possible hedge for losing range-long periods.
4. Pump-fade — bear-window research, long and short results reported
   separately.
5. Repaired trendline pair — ATT1 touch and ASB1 break/reclaim.

None of these is added to live risk solely to increase activity. Promotion
requires fee/slippage-aware OOS or walk-forward evidence and monthly loss
distribution. Existing shadow counters are retained so signal frequency is
observable while risk stays zero.

The first three follow-up sweeps are queued on the server in detached screen
`classic_next_20260618`. It waits for the active Elder process and then runs,
with one worker, `inplay_retest_v3_level_retest_repair_v2`,
`pump_fade_v5_bear_window_v1`, and
`breakdown_recent_bear_window_v2_entry_quality`. Queue output is written to
`logs/classic_next_20260618.log`. The server InPlay test passed (`8 passed`).

## 5. Alpaca version state

- `v38` is still the monthly order-driving paper executor.
- `v39` is the strongest recent-period research variant, but it failed the
  bear-2022 test and is not an order driver.
- `adaptive_v1` is the strongest bear-protection variant and currently runs
  once per trading day as `shadow_no_orders` on a virtual `$1000` allocation.
- The latest adaptive snapshot selected UNH, AAPL, JPM and LLY and estimated
  `$8362.22` as the capital required to hold every selected name in whole
  shares for native trailing orders. Fractional `$500-$1000` operation must
  use verified software protection or a cheaper-symbol universe.

The execution-validation clock for `adaptive_v1` has not started because it
does not yet submit paper orders. Shadow recommendations cannot validate
fills, cancellation, trailing exits, or broker-side protection.
