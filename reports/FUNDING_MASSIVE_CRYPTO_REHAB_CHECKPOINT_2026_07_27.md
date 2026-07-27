# Funding, Massive Basic и crypto event-rehab — checkpoint 2026-07-27

Статус: research/control-plane update only. Live core, ATT1 risk, Alpaca
positions, broker orders and exchange keys were not changed.

## Cross-exchange funding

Все текущие циклы являются paper-shadow:

- public market data only;
- no exchange API keys;
- no orders or balances;
- virtual `$100` per leg accounting only.

Обнаружена data-quality ошибка отчёта: ROI calculator смешивал 16 циклов,
закрытых до explicit-validation repair, с тремя чистыми post-fix циклами.
Исправление:

- default cohort: `explicit_validation_v1`;
- default minimum: 20 closed cycles;
- old current-model cycles remain visible as excluded evidence;
- count alone is insufficient: observed executable p25 must be strictly
  positive, otherwise status is `non_positive_executable_distribution`;
- diagnostic projection of a non-positive distribution requires an explicit
  command-line override and cannot occur by default.

Snapshot at `2026-07-27T07:17:56Z`: post-fix `N=3`, win/loss `1/2`, mean
`-0.0669%` total capital per cycle, p25 `-0.10045%`. The first five then-open
cycles begin reaching their scheduled holds from `2026-07-27T14:38:13Z`.
With continued candidate flow, 20 post-fix closes are expected approximately
between July 30 and August 3; this is data-dependent, not a promotion promise.

Historical Bybit-MEXC 180-day walk-forward was rerun over four 30-day OOS
blocks:

- zero cost: `4/4` positive, aggregate `+51.5027 bps`;
- 8 bps round trip: `3/4` positive, aggregate `+19.5027 bps`;
- 22 bps: `1/4` positive, aggregate `-36.4973 bps`;
- 40 bps: `0/4` positive, aggregate `-108.4973 bps`.

Interpretation: a gross funding differential exists, but the lane is viable
only under maker/low-cost execution. Historical funding alone cannot reproduce
basis drift, order-book capacity, two-leg fill/legging, exchange margin and
operational risk, so the paper lifecycle remains mandatory.

## Massive Stocks Basic

The owner registration/dashboard is complete. Use free Stocks Basic now:
`$0/month`, 5 REST requests per minute, two years of history, end-of-day,
reference data and corporate actions. Paid Starter/Developer are not needed
for the first Alpaca PIT/connector audit.

Safe local setup:

```bash
./START_MASSIVE_BASIC_SETUP.command
```

The key is entered through a hidden prompt, written only to the Git-ignored
`configs/massive_stocks_local.env` with mode `0600`, and never printed. The
verifier makes three requests:

1. inactive ticker reference;
2. adjusted SPY daily aggregates;
3. recent split corporate actions.

The sanitized receipt is written to
`runtime/massive_stocks_basic_audit.json`.

Two years are sufficient to verify endpoint access, PIT field semantics,
inactive symbols and corporate-action handling. They are not sufficient to
claim final long-horizon Alpaca robustness; a paid upgrade is considered only
after the free audit demonstrates that more history is the binding blocker.

## Two crypto successors

### Pump Exhaustion Unwind Short v1

This is not the old raw pump fade. Entry requires expansion, exhaustion,
bearish structure break and failed reclaim, followed by next-open execution.

Frozen strict gate:

- base: `N=39`, PF `1.410`, return `+2.143%`, DD `2.660%`;
- stress: `N=39`, PF `1.234`, return `+1.228%`, DD `3.015%`;
- holdout stress: `N=6`, PF `6.300`, net `+1.027R`;
- 13 traded and 8 positive symbols.

Verdict remains `NO_PROMOTION` because `N<40` and holdout `N<10`. The permitted
repair is new genuinely post-window event evidence with mechanics frozen, not
retuning the revealed 39 trades.

### Event Expansion First Retest Long v1

The causal long-only chain is implemented and phase-1 identity passes:
H1 expansion, later M15 hold, first retest, higher-low, strictly later BOS,
then exact next M5 open with frozen stop and cost/funding execution model.

Performance remains blocked by eight evidence contracts:

1. performance runner;
2. durable receipt-before-ACK runner;
3. funding completeness;
4. external8 market data;
5. external8 PIT metadata;
6. external8 liquidity/tradability;
7. external8 funding;
8. same-window ATT1 reference/additivity.

## Prospective event tape and automatic next step

`event_universe_v2r2` remains active public GET-only research through
`2026-07-28T18:19:58.535Z`. At `2026-07-27T07:19:03.502Z` it had sequence
`1090`; the collector continued to advance with zero live authority.

A detached post-run gate is prepared. After the bounded collector exits it
runs the already-frozen local long/short label scorer, writes a deterministic
receipt, and rebuilds:

`runtime/research/crypto_event_rehab_pair_status.json`.

This produces prospective evidence for the short pump-exhaustion and long
first-retest lanes while keeping their statistics and future risk separate.
The scorer cannot place orders or authorize promotion.

## Verification

- focused funding/Massive/crypto tests: passed;
- full suite: `1552 passed in 34.25s`;
- shell syntax, Python compile and `git diff --check`: passed.
