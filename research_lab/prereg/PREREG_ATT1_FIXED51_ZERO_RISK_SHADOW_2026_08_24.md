# ATT1 fixed-51 public zero-risk shadow preregistration

Frozen before the first ATT1 fixed-51 raw-decision event.

Authority: `research_only_no_orders_no_private_api_no_money_no_promotion`.
This collection is an evidence stream only. It cannot change the major-8
money universe, create an order, read an account, or promote a strategy.

## Frozen universes

Money remains the existing major-8:

```text
BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,LTCUSDT,DOTUSDT,SUIUSDT
```

Evidence is exactly the 51-symbol fixed list in the manifest and config. The
list is immutable after the first raw decision. `HFTUSDT` remains a frozen
member even though Bybit currently reports it stale/closed; that known gap is
recorded explicitly and is never silently substituted. Any other symbol gap is
a failing partial cycle. A zero-success cycle fails closed.

## Frozen adapter and causal contract

Each symbol uses the existing default-off `ATT1LiveEngine`. The wrapper is
rebuilt every cycle and causally replayed over at least 121 strictly contiguous
closed H1 bars so that its `first_signal_bar` and eight-hour cooldown state are
restored. Only the final closed-H1 raw decision is written. A decision must be
observed no later than 300 seconds after H1 close. All used timestamps must be
H1-aligned and contiguous; OHLCV must be finite, positive/coherent, and volume
non-negative. The ATT1 frozen short profile is unchanged: H1 signal, short
side, 6.6 ATR stop multiplier, 25%
maximum stop, 1.2R/2.5R targets, 55% first target, no break-even/trail, and
4032 five-minute-bar time stop. The exact source closure, runtime contract,
config, closed-history, final-row, and BTC-context hashes are written on every
event.

BTC H1 EMA200 is calculated causally through the same final closed H1 using
`bot.live_native_regime_gate`. `regime_eligible` is diagnostic only. It may not
admit, suppress, score, promote, size, or route a raw ATT1 decision.

The stable identity excludes Bybit observation time, response bytes, and the
still-open candle. Re-observing the same closed data/config/source decision is
idempotent. A changed closed history under the same symbol/H1 claim is an
evidence-integrity conflict and fails closed.

No backtest, private data, current account state, order response, or promotion
decision may be mixed into this evidence journal. The journal is append-only
and SHA-256 hash chained; a conflicting claim key fails closed.

## Measurement boundary

This slice records causal ATT1 raw decisions and provenance only. Every event
has `evidence_admitted=false`, `performance_authority=false`, and
`final_n_eligible=false`; statuses use the `RAW_DECISION_SHADOW_*` namespace.
It is not a performance verdict: lifecycle/fill/outcome collection, coverage,
stress-cost scoring, random control, and any canary decision require separate
preregistered gates. No count or result from this journal authorizes money.
