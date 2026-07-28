# Core control plane audit — 2026-07-28

Verdict: `FOUNDATION_PRESENT / UNIFIED_PRIORITY_WIRING_INCOMPLETE`

## Existing foundation

- D1 macro + H4 intermediate regime detector with hysteresis;
- bull trend, bull chop, bear chop and bear trend states;
- BTC dominance/alt bias context;
- strategy enable/risk allocator with freshness safe mode;
- decision bus and outcome attribution;
- sleeve edge-decay monitor;
- cross-sectional symbol ranking;
- correlation/exposure gate;
- portfolio slot and same-direction caps;
- immutable strategy-level shadow lifecycle.

This is sufficient foundation. New regime, symbol-ranking or execution features
should be evaluated by replaying immutable candidate/trade ledgers, not by
re-optimising every strategy's entry parameters.

## Actual live gap

The mirrored live allocator reports `allocator_mode=disabled` and
`allocator_effective_mode=approved_env`. It preserves approved risk, but does
not compare simultaneous candidates and award the free slots to the highest
expected after-cost value. Existing pieces therefore protect and annotate
trades, but do not yet form the desired capital dispatcher.

## Added in this change

`bot/strategy_priority_router.py` provides the missing deterministic layer:

- expected net R is discounted by evidence, regime fit, live health, execution,
  cost stress and symbol rank;
- a relative rank cannot turn non-positive expectancy into an edge;
- stale, unhealthy and unauthorized candidates are rejected with durable
  reasons;
- symbol overlap, side caps, beta-cluster caps and three slots are enforced;
- money mode requires an external authorization bit;
- the router never raises requested risk.

It is currently library + tests only. Live wiring remains prohibited until
candidate schemas from ATT1, BOUNCE1, BREAKDOWN and XSEC have exact parity and a
risk-zero replay proves that selection improves the portfolio.

## Prefix contract repair

The current regime builders still wrote the old shared `ASB1_ALLOW_*` keys.
They now emit:

- `ASLB1_ALLOW_*` for slope-break;
- `BOUNCE1_ALLOW_*` for support-bounce.

Outer `ENABLE_ASB1_TRADING` is retained as the historical slope sleeve enable
flag; direction and strategy parameters are isolated.

## BOUNCE1 server parity

- server SHA: `a6c5e8019c2c48ca5f3d06b2f2557952d77a2c67fca70dc8d0ad2d4fb6cf51ed`;
- local SHA: `d7f1508aac386e71aadd096b7715a9bac240691c68fdaa12216b24624e32b66a`;
- server SHA exactly equals the Git file immediately before prefix isolation.

The diff contains documentation and canonical-prefix readers with a legacy
`ASB1_*` fallback. Signal geometry, indicators and exit math are unchanged.
The post-change backtest already reproduced identical trades and headline
results. This is a real SHA mismatch but not a strategy-behaviour mismatch
under the frozen legacy env.

