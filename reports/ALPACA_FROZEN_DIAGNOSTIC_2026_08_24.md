# Alpaca frozen protection diagnostic — 2026-08-24

## Status and authority

This is a **research-only frozen diagnostic**. It is not a live broker result,
not a capital forecast, and it does not authorize opening Alpaca entries or
changing the live risk profile.

The run used the frozen `clean-962` contract over 501 trading sessions (25
months). The result is useful for comparing mechanics under one replay, but it
does not establish prospective paper parity, live execution parity, or the
profitability of a funded account.

The most important limitation is that the ratchet variants alter both the exit
rule and the time spent invested. The large differences below therefore cannot
be attributed to the stop alone without a preregistered, exposure-matched
replay.

## Primary comparison (5 bps cost)

| Contract | Geometric monthly | Max drawdown | Profit factor | Trades | Average gross exposure |
|---|---:|---:|---:|---:|---:|
| No ratchet, signal-anchor | 0.409% | 45.449% | 1.051 | 37 | 39.49% |
| Current 3.5% ratchet, signal-anchor | 0.847% | 23.711% | 1.270 | 40 | 10.24% |
| 3.5% ratchet, entry-relative | 1.840% | 14.365% | 1.837 | 40 | 10.53% |
| Entry-relative + 2% gap block | 1.712% | 9.206% | 2.876 | 29 | 8.91% |

The entry-relative line is a promising **hypothesis**, not a promotion result.
The gap-block line fails the minimum `N >= 30` diagnostic rule with only 29
trades. Its higher PF and lower drawdown must not be presented without that
sample-size failure.

The current 3.5% signal-anchor contract is the closest diagnostic to the
existing software behavior. Its result is materially better than the
no-ratchet comparison in this replay, but the lower average exposure means the
comparison is not a pure stop-quality test.

## 10 bps cost stress

The same frozen replay at 10 bps remains directionally similar:

| Contract | Geometric monthly | Max drawdown | Profit factor | Trades |
|---|---:|---:|---:|---:|
| No ratchet, signal-anchor | 0.358% | 45.745% | 1.040 | 37 |
| Current 3.5% ratchet, signal-anchor | 0.794% | 23.800% | 1.249 | 40 |
| 3.5% ratchet, entry-relative | 1.789% | 14.434% | 1.809 | 40 |
| Entry-relative + 2% gap block | 1.675% | 9.268% | 2.820 | 29 |

The 10 bps stress is still a model assumption. It is not a substitute for
measured Alpaca fills, spread, partial fills, borrow/availability effects, and
overnight gap execution.

## Whole-share diagnostic (not a promotion run)

Flooring quantities to whole shares changes both sizing and candidate
selection. It is therefore a useful operational diagnostic for whether a
whole-share/GTC profile is feasible, not an apples-to-apples performance claim.

| Whole-share contract | Geometric monthly | Max drawdown | Profit factor | Trades |
|---|---:|---:|---:|---:|
| 3.5% ratchet, signal-anchor | 0.835% | 23.181% | 1.302 | 35 |
| 3.5% ratchet, entry-relative | 1.816% | 12.243% | 2.034 | 35 |
| Entry-relative + 2% gap block | 1.737% | 9.097% | 3.876 | 25 |

The gap-block whole-share variant fails the same `N >= 30` rule even more
clearly. Whole-share selection also leaves budgets unusable when a candidate
cannot buy one share and can reduce the number of simultaneous positions. Any
claim that whole shares improve returns must first fix the candidate-selection
and budget-allocation contract, then replay it prospectively.

## Data inventory and quality

The local cache contains 61 files. The frozen contract requires 58 files (57
symbols plus `SPY`). The three extra files are `IWM`, `QQQ`, and `SQ`. The
`XYZ` file has shortened coverage. This means the cache is not a clean
interchangeable universe: the exact frozen manifest and coverage boundaries
must be recorded with each replay.

The files described by the run as OHLC are approximately hourly in this
diagnostic; they are not an intraday fill tape. The replay consequently cannot
prove the exact behavior of a 15-minute manager, native trailing order, or a
gap whose path is unknown between bars.

## What this does and does not support

It supports:

* keeping the monotonic stop-floor invariant as a safety requirement;
* treating entry-relative ratcheting as the next falsifiable Alpaca research
  candidate;
* testing whole-share sizing and GTC eligibility in a default-off paper
  profile;
* prioritizing measured exposure, gap handling, cost stress, and candidate
  selection rather than optimizing a single headline PF.

It does **not** support:

* unfreezing Alpaca money entries;
* claiming a 4–5% monthly return target is attainable;
* switching the live manager to entry-relative stops or native trailing;
* claiming an executable overnight floor while the broker order is `DAY` and
  cannot trigger outside regular market hours (it may remain accepted/queued);
* treating a 29-trade gap-block result as validated.

## Required next gate

Before any promotion, run a preregistered, exposure-matched replay with:

1. the exact live candidate universe and selection timestamp;
2. the exact live quantity, fractional/whole-share, and cash rules;
3. broker-native order semantics, including `DAY` expiry, GTC eligibility,
   partial fills, replacement/restart behavior, and overnight gaps;
4. measured spread/slippage stress including 5 and 10 bps;
5. stop-floor monotonicity across restart, session boundary, and re-arm;
6. prospective paper parity with signal, fill, protection, adjustment, and
   exit receipts; and
7. a holdout and concentration report with a minimum trade-count gate.

Only after that replay is clean, the paper lifecycle is observed, and live
broker truth agrees with the deployed hash may a tiny, explicitly approved
canary be considered.
