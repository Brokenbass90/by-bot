# InPlay V4 helper wiring — 2026-07-01

Status: implemented behind env flags, research-only. Default InPlay V4 behavior
is unchanged unless a flag is explicitly enabled.

## What changed

`strategies/inplay_retest_v4.py` can now use the shared helper layers:

- `bot.retest_quality.score_retest`
- `bot.range_filter.range_state`
- `bot.elder_filter.elder_bias`
- `bot.breakout_confirm.breakout_confirm`

The goal is to stop maintaining separate hand-written logic for every level
strategy and test one consistent definition of:

- good retest quality;
- correct range/bounce side;
- Elder tide permission;
- confirmed breakout before a flip retest.

## New env flags

- `IRV4_USE_RETEST_QUALITY=1`
- `IRV4_RETEST_MIN_QUALITY=0.55`
- `IRV4_USE_RANGE_FILTER=1`
- `IRV4_RANGE_REQUIRE_ALL=0`
- `IRV4_USE_ELDER_FILTER=1`
- `IRV4_ELDER_HTF_TF=240`
- `IRV4_ELDER_REQUIRE_WITH_TIDE=0`
- `IRV4_USE_BREAKOUT_CONFIRM=1`
- `IRV4_BREAKOUT_LOOKBACK=60`
- `IRV4_BREAKOUT_EVENT_WINDOW=8`
- `IRV4_BREAKOUT_BUFFER_ATR=0.25`
- `IRV4_BREAKOUT_VOL_MULT=1.3`

## Setup A behavior

Setup A remains support/resistance bounce/retest. If helper flags are enabled:

- retest must pass `score_retest`;
- range filter must allow the same side;
- Elder filter must not block the side.

Long support retest uses `long_ok`; short resistance retest uses `short_ok`.

## Setup B behavior

Setup B remains broken-level flip retest. If helper flags are enabled:

- retest must pass `score_retest`;
- a recent prior breakout must be confirmed by `breakout_confirm`;
- Elder filter must not block the side.

## Tests

Focused suite:

```bash
.venv/bin/python -m pytest \
  tests/test_inplay_retest_v4.py \
  tests/test_retest_quality.py \
  tests/test_breakout_confirm.py \
  tests/test_elder_filter.py \
  tests/test_range_filter.py \
  tests/test_spike_fade_v3.py
```

Result: `44 passed`.

## Research recommendation

Run A/B OOS, not live-risk:

1. baseline V4;
2. `USE_RETEST_QUALITY=1`;
3. `USE_RETEST_QUALITY=1 + USE_RANGE_FILTER=1`;
4. `USE_RETEST_QUALITY=1 + USE_ELDER_FILTER=1`;
5. Setup B only with `USE_BREAKOUT_CONFIRM=1`.

Judge by OOS folds, monthly stability and symbol concentration, not by one PF
peak.
