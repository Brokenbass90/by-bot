# Income Live Roadmap — 2026-04-28

## Goal

Get a small healthy live portfolio trading first, then expand only from verified
evidence. Speed matters, but the bot must not recover income by reintroducing
uncontrolled loss engines.

## Current Truth

- Server is alive: bot heartbeat fresh, allocator/router OK, safe mode off, no
  open trades.
- Alpaca v38 hybrid is the cleanest equity sleeve, but it is a compounding
  sleeve, not an income engine: about `22-28%` annualized in the current tests.
- Crypto has the biggest income upside, but the old golden stack is not
  currently reproduced:
  - expected golden v5: `+89.65%`, PF `2.121`, DD `2.88%`, `427` trades
  - current reproduced run: `+8.40%`, PF `1.089`, DD `7.98%`, `294` trades
- First current income candidate found:
  - `ATT1 + ARF1/flat + breakdown_v1 + btc_eth_midterm_pullback`
  - 365d to 2026-04-25: `+70.17%`, PF `1.545`, DD `6.23%`, `445` trades
  - recent 180d: `+50.98%`, PF `1.805`, DD `3.76%`, `236` trades
  - details: `docs/CRYPTO_INCOME_STATIC_V1_20260428.md`
- First dynamic control-plane candidate:
  - `ATT1 + ARF1/flat + btc_eth_midterm_pullback`
  - v1 replay, 11 populated monthly windows: `+45.30%`, PF `1.489`,
    DD `5.77%`, `454` trades, `1` red month
  - v2 replay with v7 cut and ARF1 bull_chop guard: `+45.44%`, PF `1.493`,
    DD `5.95%`, `456` trades, `1` red month
  - deployed canary: `configs/crypto_income_live_canary_v2.env` +
    `configs/portfolio_allocator_policy_canary_v2.json`
- Main crypto regression targets:
  - `alt_inplay_breakdown_v1`: old contributor `+34.24`, current `-7.00`
  - `inplay_breakout`: old contributor `+17.41`, current `-1.63`
- Range is paused after a live loss and should not be expanded until it passes
  annual + additivity again.

## Live First Package

Live is now narrow while repair is happening:

1. Keep `ATT1`, `flat/ARF1`, and `btc_eth_midterm_pullback` as the live canary
   core while validation runs.
2. Keep `range` disabled for new entries.
3. Keep `breakdown_v1` out of live for now. Static ER-gated results are good,
   but dynamic attribution is still negative.
4. Do not add `inplay`, `range_package`, or broad relaxed packages until their
   current annual regression is repaired.
5. Let Alpaca paper continue on the v38/hybrid path, but do not move real money
   before broker-side protective order handling is added.

## Promotion Gates

For a strategy to enter low-risk crypto canary:

- 360d/annual PF `> 1.25`
- annual drawdown `< 8%`
- enough trades to matter, target `50+` unless the sleeve is deliberately slow
- positive additivity inside the portfolio, not just standalone profit
- no hidden dependence on stale router/regime/allocator files

For a strategy to become a normal live sleeve:

- recent annual pass
- walk-forward pass
- multi-year or multi-regime sanity check
- live execution path confirmed against backtest assumptions

## Work Order

1. Repair crypto regression before adding new risk.
   - Compare golden v5 trades vs current reproduced trades.
   - Start with `alt_inplay_breakdown_v1`, then `inplay_breakout`.
   - Identify whether drift comes from strategy code, engine defaults, symbol
     routing, macro/regime filters, or changed exits.

2. Rebuild a small crypto portfolio.
   - First candidate: `ATT1 + ARF1/flat + BTC/ETH midterm`.
   - `inplay_breakout` stays in repair until it has positive current additivity.
   - `breakdown_v1` stays in repair until dynamic attribution turns positive.
   - Second candidate: add `ASB1` or `IVB1` only after testing soft-router /
     control-plane bypass variants.
   - Elder is used first as a filter/regime tool, not as a trade engine, until
     it has tradeful WF evidence.

3. Keep Alpaca as two lanes.
   - Conservative lane: preserve v38 hybrid for future larger capital.
   - Income research lane: continue intraday/swing research, but do not force
     the monthly sleeve into overtrading.

4. Harden operations.
   - Web stays private via server localhost + SSH tunnel.
   - Watchdogs keep heartbeat/control-plane fresh.
   - AI may audit, propose, compare, and summarize evidence, but live changes
     require explicit approval and a rollback path.

## Immediate Next Step

Monitor the deployed `crypto_income_live_canary_v2`:

- 48-72h live watch: heartbeat, WebSocket messages, open trades, trade events,
  and `ATT1`/`flat`/`midterm` attempt/no-signal counters.
- Confirm no disabled sleeves (`breakdown`, `range`, `ivb1`, v7, `vwap`) appear
  in live strategy flags or trade events.
- Refresh `.cache/klines` so the April 2026 dynamic window is not skipped.
- Continue golden v5 regression repair in parallel; do not expand live risk
  until the canary produces clean live evidence.

Deploy note, 2026-04-28:

- Server backup stamp: `20260428_170228`.
- `.env` backups: `state/env_backups/.env.20260428_170228.bak` and
  `state/env_backups/.env.20260428_170353.bak`.
- Policy/health backups:
  `runtime/server_backups/*before_crypto_canary_v2_20260428_170228.*`.
- `bybot.service` restarted successfully; heartbeat fresh; `ws_guard=0`;
  Bybit messages flowing; open trades `0`.
