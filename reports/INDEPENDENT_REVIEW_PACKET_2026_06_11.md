# Independent Review Packet — 2026-06-11

Purpose: get an external technical/trading review of the strategies we should improve rather than discard. This packet focuses on three candidates where the architecture matters more than simple parameter tuning.

## 1. Pair Stat-Arb

Files:
- `strategies/pair_stat_arb_v1.py`
- `strategies/pair_arb_executor_v1.py`
- `scripts/pair_arb_scanner.py`
- `scripts/validate_pair_arb.py`
- `scripts/walkforward_pair_arb.py`
- `scripts/fast_pair_research.py`
- `tests/test_pair_stat_arb.py`
- `tests/test_pair_arb_executor.py`
- `tests/test_validate_pair_arb.py`
- `tests/test_pair_arb_scanner.py`

Current diagnosis:
- Old PF 4.78 was a measurement artifact: validator used a re-fitted spread at exit, which is not directly realizable by the executor.
- Validator was rewritten to realized two-leg P&L.
- Current local checks are weak: ETH/BTC PF 0.0 on 361 aligned 1h bars; LINK/ETH PF about 0.99 and fee-fragile.

Known weaknesses to review:
- beta stability gate is missing or insufficient;
- signal and executor may still disagree if signal is beta-weighted but execution is equal-notional;
- fixed z thresholds ignore spread volatility regime;
- pair universe is too small;
- no meta-regime gate despite recent windows being better than older windows.

Questions for reviewer:
- What is the correct realized P&L formulation for beta-weighted crypto perp pair trading?
- Should execution use beta-weighted notional, vol-targeted notional, or equal-notional?
- Which stationarity/beta-stability tests should be required before entry?
- How should walk-forward select pairs and parameters without overfitting?
- What fee/slippage assumptions make this strategy worth paper trading?

## 2. Liquidity Sweep Map / LSR1

Files:
- `bot/liquidity_map.py`
- `scripts/backtest_candidates.py`
- `tests/test_liquidity_map.py`

Current design:
- stop pools are inferred from equal highs/lows on fractal pivots;
- pools are built on higher timeframe candles (`htf_factor=4`);
- execution timeframe is 1h;
- entry is after wick sweep and close back inside the pool;
- stop is beyond wick extreme, target is 2R.

Current local results:
- all available core9 symbols: PF 1.116, 78 trades, 9 positive months out of 13;
- filtered basket LINK/ADA/LTC/DOT: PF 2.424, 32 trades, 9 positive months out of 12;
- weak symbols: BTC, ETH, SUI; BNB data missing locally.

Known weaknesses to review:
- symbol selection may be doing too much work;
- no liquidation/funding confirmation yet;
- no explicit strong-trend continuation filter;
- candidate backtest is standalone, not yet portfolio slot-tested against ATT1.

Questions for reviewer:
- Is the HTF-pool/LTF-sweep design structurally sound?
- What trend/regime filters should prevent fading strong continuation moves?
- Should stop/target remain fixed 2R or switch to pool-to-pool targets?
- How to test additivity against ATT1 without slot/capital collision?

## 3. Alpaca Active Swing With Trailing

Files:
- `strategies/equities_swing_active_v1.py`
- `scripts/validate_swing_alpaca.py`
- `tests/test_equities_swing_active.py`
- `configs/alpaca_v38_hybrid_top4_candidate.env`
- `configs/alpaca_v38_active_paper_candidate.env`
- `configs/alpaca_v38_more_active_research.env`

Current diagnosis from strategy package:
- baseline swing: 456 trades, PF 1.117, expectancy +0.223% per trade;
- trailing 2.0 ATR on short hold hurt performance: PF 1.017;
- trailing 2.5 ATR + breakeven after +1R, hold 15 days, rebalance every 3 days: 755 trades, PF 1.235, expectancy +0.408% per trade;
- PDT-safe because holding period is multi-day.

Known weaknesses to review:
- needs walk-forward on a wider universe;
- must not conflict with monthly v38 positions;
- needs broker-side protection audit for every paper fill;
- PF is still modest and may be sensitive to universe construction.

Questions for reviewer:
- Is 2.5 ATR trailing + BE@1R a robust exit model or likely overfit?
- How should the strategy split capital with monthly v38?
- What minimum paper evidence is required before real $500 deployment?
- Which market-regime gates should suppress entries during equity bear phases?

