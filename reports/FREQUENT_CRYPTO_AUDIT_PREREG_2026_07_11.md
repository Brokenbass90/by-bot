# Frequent crypto sleeves: audit and frozen research — 2026-07-11

## Executive verdict before new outcomes

Only two bounded causal questions are worth more compute now:

1. `alt_range_scalp_v1` (ARS1 / Bollinger-boundary "pila"), physically split
   into long-only and short-only, with one change: `ADX off -> ADX <= 25`.
2. `alt_support_bounce_v2` (ASB2 / shared horizontal and channel support),
   long-only, with one change: block descending channels.

This is research-only. Neither candidate is live-ready even if the numerical
gate passes, because live parity gaps remain. ARF1/ARF2, Elder, ASB1 and ASR1
are not being re-swept: the existing evidence already answers their present
versions or their runtime contract is not trustworthy enough.

Frozen preregistration:
`configs/preregistered/frequent_crypto_20260711.json`.

Runner:
`scripts/run_frequent_crypto_preregistered_20260711.sh`.

## Data truth

Strict preflight was run before choosing outcome-dependent symbols:

- required coverage: `>= 98%` of 5-minute bars;
- maximum internal gap: `<= 12` bars;
- window: `360d` ending `2026-07-04`;
- cache: `data_cache`, network fetch forbidden by `BACKTEST_CACHE_ONLY=1`.

PASS universe, frozen without result-based removal:

`BTCUSDT, ETHUSDT, ATOMUSDT, AVAXUSDT, BNBUSDT, XRPUSDT, DOGEUSDT,
BCHUSDT, XLMUSDT, 1000PEPEUSDT, HYPEUSDT, TAOUSDT, ONDOUSDT`.

The first broad preflight correctly rejected `SOL/ADA/LINK/LTC/SUI` for a
1,033-bar internal gap, `DOT` for only 93.6% coverage and `NEAR` for only 5.4%.
Those symbols are not silently retained.

Preflight evidence:

- `reports/research/preflight_frequent_crypto_360d_20260711.csv`
- `reports/research/preflight_frequent_crypto_alt_360d_20260711.csv`

## Causality and execution audit

### Backtest clock

`backtest.engine.KlineStore` exposes only completed higher-timeframe candles at
the current execution-bar boundary. Every new run additionally uses
`--entry-on-next-open`; this removes same-close fills after seeing the completed
signal candle. Base costs are 6 bps fee + 2 bps slippage per side. Stress costs
are 10 + 5 bps per side.

### ARS1 / range scalp

- Code is deterministic and consumes completed 15m candles in backtest.
- Long and short switches exist (`ARS1_ALLOW_LONGS/SHORTS`) and are now tested
  in physically separate processes.
- It uses Bollinger boundaries, not the project's clustered horizontal/sloped
  level engine. It is a statistical range edge, not proof of quality levels.
- Existing honest next-open result was promising but not promotable: 108 trades,
  PF 1.682, +16.61, DD 6.68; both directions were aggregate-positive, but the
  candidate failed red bear months and its control-plane stack worsened it.
- The new causal question is whether a canonical `ADX <= 25` gate removes trend
  breakouts rather than merely cutting frequency.
- **Live parity FAIL:** `ENABLE_RANGE_TRADING` in the monolith executes
  `sr_range_strategy.RangeStrategy`, while research uses
  `strategies.alt_range_scalp_v1.AltRangeScalpV1Strategy`. Current Telegram and
  sleeve naming can make them look identical, but they are different systems.
  A numerical PASS cannot go to live until a dedicated closed-bar ARS1 adapter
  and parity replay exist.

Frequency expectation frozen before outcome: roughly `20-120` trades per side
per year across the 13-symbol universe. Lower is too sparse; materially higher
likely means the range filter is not filtering.

### ARF1 / ARF2 horizontal resistance fade

- ARF1 is a real horizontal short-only fade: the resistance/support extrema are
  computed from prior 1h bars (`[:-1]`), then a closed rejection bar confirms.
- Its live wrapper now uses `fetch_closed_klines`, so class-level live/backtest
  parity is materially better than the other old wrappers.
- ARF2 has richer repeated-pivot clusters, volume-density/HVN, optional unified
  levels, range state, retest quality, failed-breakout and Elder filters.
- But this family has already consumed the relevant test: the recent strict
  follow-up passed temporal/unseen-symbol checks and then failed stressed PF
  (`~1.003`) and concentration. ASB2/ARF2 OOS evidence is also recorded as
  no-go. Re-running another parameter grid would be selection bias, not useful
  research. Excluded from this queue.

### ASB1 / ASR1 legacy support bounce and reclaim

- Both use prior-bar horizontal support/resistance and are logically long-only.
- Their live wrappers pass raw Bybit klines and do not use the shared
  `fetch_closed_klines` adapter. Live can therefore see a still-forming 1h/4h
  bar that the backtest never sees.
- `ASB1_*` is also shared with the unrelated `alt_slope_break_v1`, while the
  scheduler sleeve is named `BOUNCE1_*`. Effective configuration can collide.
- ASR1's current 96-run next-open repair produced zero trades. It is not a money
  candidate until filter diagnostics and the live closed-bar contract are fixed.
- ASB1's older attractive rows were legacy signal-price fills, not the current
  promotion contract. Excluded from the queue.

### ASB2 shared-level bounce

- Uses the shared `bot.market_context` layer: clustered horizontal supports,
  confirmed pivots, channel regime, optional freshness, volume and HVN
  confluence. This is the best existing answer to "quality levels".
- It is explicitly long-only but currently permits descending channels by
  default, using only a nearer TP. That is the single causal defect tested here.
- Prior 360d smoke with all regimes was decisively bad (`580` trades, PF `0.756`,
  -32.18) and used signal-price entry. The new candidate does not tune the
  detector; it only disables descending regimes and applies next-open/stress.
- There is no production live adapter/sleeve for ASB2. Even PASS means research
  evidence only.

Frequency expectation frozen before outcome: `80-400` annual trades before the
absolute gates. The descending block should reduce the old excessive cadence
substantially. If it does not, the channel classifier is not doing useful work.

### Elder

- V2 and V3 share the causal completed-timeframe backtest contract and have
  explicit long/short switches.
- Evidence is consistently negative/fragile: V3 relaxed 360d examples are below
  PF 1, the best mass sweep pockets are small-N/legacy, and the pattern scorecard
  records large DD failures.
- **Live parity FAIL:** the monolith's `ENABLE_ELDER_TRADING` still instantiates
  and health-gates `elder_triple_screen_v2`; research repairs target V3.
- Elder should remain an advisory/filter feature, not an independent money
  engine. No additional Elder sweep is launched.

### InPlay

InPlay has a separate current inventory/audit. Existing strict maker/retest
results are not sufficient for promotion, so it is deliberately not duplicated
inside this compute queue.

## Promotion discipline

Each side must pass annual base, annual stress and fresh 90-day stress gates
independently. A combined profitable total cannot hide a losing side. A causal
candidate must also beat its same-universe control without removing more than
70% of trades. Any failure is `NO_PROMOTION`. Full success is still only
`RESEARCH_PASS`: live class parity, closed-bar adapter, exact execution replay
and risk-zero shadow are separate mandatory steps.
