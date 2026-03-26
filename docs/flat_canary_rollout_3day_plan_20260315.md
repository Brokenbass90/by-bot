# Flat Canary Rollout Plan (3 Days)

## Current honest status

- strongest branch right now: `alt_sloped_channel_v1` flat slope-short family
- verified canary-quality research result:
  - `LINKUSDT + ATOMUSDT` base: `+11.56`, PF `3.849`, winrate `70.0%`, DD `1.79`
  - `LINKUSDT + ATOMUSDT` cost-stress: `+10.02`, PF `3.209`, winrate `65.0%`, DD `2.01`
  - `ATOMUSDT` only base: `+7.75`, PF `4.050`, winrate `69.2%`, DD `0.98`
  - `ATOMUSDT` only cost-stress: `+6.75`, PF `3.359`, winrate `61.5%`, DD `1.11`
- important blocker:
  - `alt_sloped_channel_v1` is wired into `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py`
  - it is **not** yet wired into `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py`
- practical meaning:
  - the first rollout step is not "enable on server immediately"
  - the first rollout step is a minimal live wiring / isolated sidecar for the flat canary

## What to deploy first

Deploy first:

- `ATOMUSDT` only
- short-only
- tiny canary risk
- isolated sleeve / sidecar

Why first:

- best smoothness of the whole family
- `0` negative months in research
- lower DD than the pair
- simplest possible live verification before adding a second symbol

Do **not** deploy first:

- `BTC` add-on branch
- horizontal flat family
- broad flat router

These are still research-only.

## Tiny canary mode

### Phase 1: Day 1

- sleeve: `ATOMUSDT` only
- side: short-only
- risk per trade: `0.10%` equity
- max concurrent flat positions: `1`
- keep the current live core unchanged
- run the flat canary as a separate sleeve, not by weakening existing live logic

### Phase 2: Day 2

If Day 1 is clean:

- expand allowlist to `ATOMUSDT,LINKUSDT`
- keep short-only
- keep risk per trade at `0.10%`
- keep max concurrent flat positions at `1`

### Phase 3: Day 3

If Day 2 is still clean:

- keep `ATOMUSDT + LINKUSDT`
- decide whether to:
  - continue at `0.10%` and gather more evidence
  - or lift to `0.15%` only if execution and behavior match research closely

## Hard stop conditions

Disable the flat canary immediately if any of these happens:

- repeated infrastructure issue:
  - `NO_CONNECT`
  - or `2` consecutive `CRITICAL` windows tied to the canary process
- strategy trades a symbol outside the canary allowlist
- strategy opens a long even though the canary is short-only
- more than `1` concurrent flat canary position is opened
- realized canary sleeve loss reaches `-0.75%` equity before the canary is approved
- `3` full-stop losses without meaningful partial progress (`TP1`) inside the first `10` canary trades

## Soft pause / review conditions

Pause and review before disabling permanently if:

- `2` losing days in a row appear in the first canary window
- there are `2` losses from the same symbol in a tight cluster
- fills/slippage look materially worse than the stress replay assumptions
- the canary produces structurally different trades from research

## What counts as a successful canary

The canary is successful if all of the following are true:

- no hard-stop event occurred
- runtime stayed operational and calm
- only the intended symbols were traded
- entry direction and trade frequency look consistent with research
- no obvious cluster-loss pathology appeared

Performance check:

- if fewer than `3` trades occur, extend the canary; do not call it a failure
- if `3+` trades occur, prefer:
  - net PnL non-negative
  - no more than `2` full-stop losses
  - no ugly same-day loss cluster

## Exact research profile to carry into live wiring

Current winning profile:

- `ASC1_ALLOW_LONGS=0`
- `ASC1_ALLOW_SHORTS=1`
- `ASC1_MAX_ABS_SLOPE_PCT=2.0`
- `ASC1_MIN_RANGE_R2=0.25`
- `ASC1_SHORT_MAX_NEAR_UPPER_BARS=2`
- `ASC1_SHORT_MIN_REJECT_DEPTH_ATR=0.75`
- `ASC1_SHORT_MIN_RSI=60`
- `ASC1_SHORT_NEAR_UPPER_ATR=0.15`
- `ASC1_SHORT_MIN_REJECT_VOL_MULT=0.0`
- `ASC1_TP1_FRAC=0.45`
- `ASC1_TP2_BUFFER_PCT=0.40`
- `ASC1_TIME_STOP_BARS_5M=480`

## Immediate roadmap

### Today

- keep live core as-is
- do not rush BTC into canary
- prepare flat canary wiring path
- keep refining the second flat family separately

### Next 3 days

1. wire `alt_sloped_channel_v1` into live bot or a thin isolated live sidecar
2. launch `ATOMUSDT` tiny canary
3. expand to `LINKUSDT + ATOMUSDT` only if Day 1 is clean
4. keep BTC and the second flat family in research until they show the same level of stability

## Priority after the first canary

1. finish the second flat family (`horizontal resistance fade`)
2. build a family-router instead of a permanent fixed list
3. move Alpaca/equities to paper/canary once the smooth branch holds around `2-3` red months
