# Red-Month Hedge + Inplay Retest v3 Audit (2026-06-17)

## Current live truth

- Crypto bot is live (`DRY_RUN=false`) and partially unfrozen.
- Active live risk:
  - `range` / пила от границ флэта: `RANGE_RISK_MULT=0.25`
  - `flat` / шорт от сопротивления: `FLAT_RISK_MULT=0.30`
- Telemetry/shadow only:
  - `ivb1` / старый импульсный пробой: `IVB1_RISK_MULT=0.00`
  - `att1`, `breakdown`, `bounce1`, `midterm`: enabled flags may be true, but current risk is `0.00`.
- Zero-risk sizing bug fixed: `risk_mult <= 0` now returns zero notional globally.

## Inplay Retest v3 audit inputs

Files to review:

- `strategies/inplay_retest_v3.py`
- `tests/test_inplay_retest_v3.py`
- `configs/autoresearch/inplay_retest_v3_level_retest_repair_v1.json`
- `reports/IVB1_INPLAY_LOGIC_REVIEW_2026_06_16.md`

Known issue from first smoke:

- First soft v3 candidates produced `net=-100`, `DD≈100%`.
- This is not a proof that the idea is dead; it means the current execution/backtest parameter surface can still create catastrophic trade streams.
- Next fix direction: inspect trade stream before broad sweep:
  - entry too far from actual level vs intended limit-at-level;
  - stop too tight/wide under 15m execution;
  - no trend/regime guard on continuation setups;
  - TP1/opposing-level selection too optimistic or wrong side;
  - position sizing/exits under runner path.

## Red-month hedge audit

Goal: not just maximize annual return, but reduce red bear/chop months so the portfolio can scale.

Audit targets, in order:

1. `range v3` / пила от границ флэта
   - Current local research already has PASS pockets around `+14%..+17%` on $100 annual smoke, PF `~1.58..1.69`, DD `~6.6`.
   - Main failure: `neg_months>4`.
   - Audit: identify which months lose and which regime/ADX/BTC trend conditions cause losses.

2. `breakdown` / слом поддержки
   - Candidate hedge for months where range loses because market breaks down instead of bouncing between borders.
   - Audit: short-only, bear/bear-chop windows first, monthly table required.

3. `elder EMA50` / тройной экран по тренду
   - Candidate hedge for long trend months where mean reversion bleeds.
   - Audit: 4h/1h trend alignment, one trade per symbol per day, monthly table required.

4. `VWAP mean reversion`
   - Candidate replacement/companion for range in intraday flat.
   - Audit: only high-liquidity symbols, sessionless crypto VWAP, strict volatility gate.

5. `funding/pair carry`
   - Non-directional hedge for months where directional sleeves are noisy.
   - Audit: net after double fees, spread, hedge drift, worst rolling windows.

## Promotion rule

Candidate can move toward canary only if:

- yearly net positive after fees/slippage;
- PF > 1.2 preferred;
- DD controlled below ~8-10% in $100 research scale;
- red bear months reduced or covered by another sleeve;
- stack comparison proves the bot foundation is not choking the strategy.

