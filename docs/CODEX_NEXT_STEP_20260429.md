# Codex Next Step — 2026-04-29

## Current Live Baseline

`crypto_income_live_canary_v2` is the active crypto baseline.

Live sleeves:
- `alt_trendline_touch_v1` / ATT1
- `alt_resistance_fade_v1` / ARF1 flat
- `btc_eth_midterm_pullback`

Explicitly not live yet:
- `breakdown_v1`
- `range_scalp_v1`
- `impulse_volume_breakout_v1`
- `elder_triple_screen_v3`
- v7 sleeves

Reason: canary v2 has the cleanest dynamic replay so far:
- about `+45%` 360d
- PF about `1.49`
- max DD about `6%`
- one red month

## Main Decision Today

Do not expand live by adding a whole strategy family blindly. Expand only if a
side-specific candidate improves portfolio additivity versus canary v2.

Priority order:

1. `range_scalp_v1` split LONG/SHORT
2. `alt_sloped_channel_v1` split LONG/SHORT
3. `ARF1` versus `ASB1` bull-regime swap
4. `impulse_volume_breakout_v1` r073 WF-22
5. ATT1 density replacement only after the safer sleeves are tested

## Running Now

Pair 1 autoresearch completed:

- `configs/autoresearch/range_scalp_long_only_v1.json`
- `configs/autoresearch/range_scalp_short_only_v1.json`

Each sweep had 144 combinations over 360d. Acceptance before any live promotion:

- standalone net >= `+5`
- PF >= `1.20`
- DD <= `10%`
- enough trades
- dynamic additivity versus canary v2 must not reduce net return
- dynamic additivity DD increase must be <= `+1.5pp`

Results:

| Case | Best | Standalone verdict |
|---|---:|---|
| LONG-only | `+16.17`, PF `2.354`, DD `5.831`, 57 trades | rejected: 5 negative months and 4-month negative streak |
| SHORT-only | `+6.36`, PF `1.633`, DD `2.798`, 47 trades | passed standalone gate |

Best SHORT-only params:

```env
ARS1_ALLOW_LONGS=0
ARS1_ALLOW_SHORTS=1
ARS1_MIN_BAND_WIDTH_PCT=2.5
ARS1_RSI_SHORT_MIN=65
ARS1_SL_ATR_MULT=0.8
MAX_POSITIONS=3
```

Dynamic additivity versus canary v2:

| Case | Return | PF | DD | Red months | Trades | Range attribution | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| canary v2 baseline | `+45.44%` | `1.4927` | `5.9475%` | `1` | `456` | n/a | current live |
| range short, dynamic router | `+38.38%` | `1.3914` | `6.7075%` | `2` | `481` | `-1.8189` | reject |
| range short, fixed ARS1 basket | `+45.50%` | `1.4541` | `6.6743%` | `3` | `494` | `+4.6915` | no live promotion yet |

Important finding: the general dynamic router widens ARS1 into symbols that were
not in the standalone winner basket and turns attribution negative. Fixed ARS1
basket repairs attribution, but it does not improve the total portfolio enough
to justify canary v3 today.

Conclusion:

- keep `ENABLE_RANGE_TRADING=0` in live canary for now
- do not promote `range_scalp_v1` today
- next useful repair is not another raw ARS1 parameter sweep; it is either:
  - a policy-level low-risk/fixed-basket ARS1 test, or
  - a regime/month hygiene filter for LONG-only, which has raw edge but bad red-month structure
  - otherwise move to Pair 2 sloped split

## Breakdown Verdict

`breakdown_v1_recent180_focus_v1` is not ready for live. The 180d edge was real,
but the 330d and WF-22 checks weakened it enough to treat it as unstable/recent
overfit rather than a clean control-plane casualty.

Current verdict:
- do not deploy old breakdown candidate
- research a new WF-gated breakdown/breakout pair instead
- only promote after additivity improves canary v2

## Alpaca Verdict

Best current Alpaca candidate is still the monthly v38 hybrid:

- OOS annual return about `+28%`
- PF about `7.85`
- WR about `87%`
- DD about `-2.3%`
- too few trades for income

This is a compounding sleeve, not a paycheck sleeve.

For a future `$500` deposit:

1. Use v38 hybrid first, in paper and then very small live only after broker-side
   stop/trailing protection is implemented.
2. Do not use swing classic: current sweep is strongly negative.
3. Do not use intraday v3 yet: shadow WF output was empty, so it is not validated.
4. Continue searching for an income sleeve separately: either repair swing_strict
   or build a new intraday lane with real WF evidence.

## AI Operator Direction

Use AI as a shadow-mode final gate first, not as a direct trader:

- strategy creates a valid signal
- AI receives context and writes approve/block/reduce decision to log
- live ignores AI verdict for at least one week
- after enough evidence, compare simulated AI-gated trades against baseline

No AI-generated live orders and no AI global-risk changes.

## Next Commands After Pair 1 Finishes

Pair 1 did not pass portfolio promotion. Next:

1. Leave `ENABLE_RANGE_TRADING=0`.
2. Start Pair 2 sloped LONG/SHORT autoresearch.
3. Keep canary v2 unchanged until the next additive sleeve passes.
4. If revisiting range, change policy-level ARS1 risk/basket logic, not only env.
