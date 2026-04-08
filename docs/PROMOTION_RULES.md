# Crypto Promotion Rules

This file is the explicit promotion gate for crypto package changes.

Do not promote a sleeve or package from one good chart, one good `180d` run,
or one isolated strategy result.

## Required Evidence

Every candidate package must clear all three gates:

1. Annual gate
- run a full `360d` package summary
- require:
  - positive net pnl
  - acceptable profit factor
  - acceptable max drawdown
  - enough trades to matter

2. Walk-forward gate
- run rolling walk-forward on the same package
- require:
  - enough windows
  - enough passed windows
  - positive average net pnl
  - acceptable average drawdown

3. Portfolio compare gate
- compare the candidate package against the current golden annual baseline
- promotion is allowed only if the candidate:
  - does not materially regress return / PF / DD
  - and clears at least one explicit improvement path

## Single Source Of Truth

- Policy file:
  - [crypto_promotion_policy.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/crypto_promotion_policy.json)
- Evaluator:
  - [evaluate_crypto_promotion.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/evaluate_crypto_promotion.py)
- Current golden baseline reference:
  - [GOLDEN_PORTFOLIO_BASELINES.md](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/GOLDEN_PORTFOLIO_BASELINES.md)

## Standard Command

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate
python3 scripts/evaluate_crypto_promotion.py \
  --annual-summary backtest_runs/<candidate>/summary.csv \
  --walkforward-latest backtest_runs/<walkforward>/walkforward_latest.json
```

The evaluator defaults to the current reproducible golden annual baseline:
- [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_archive/portfolio_20260328_233022_full_stack_baseline_20260328_v5_dynamic_allowlist_recent_annual/summary.csv)

## Practical Meaning

- `annual PASS` + `walk-forward FAIL` = not promotable
- `annual PASS` + `walk-forward PASS` + `portfolio compare FAIL` = still not promotable
- only `annual PASS` + `walk-forward PASS` + `portfolio compare PASS` may move to canary / live discussion

## Why This Exists

The bot already showed that:
- `180d` can look strong while `360d` is weak
- single sleeves can look alive while the package degrades
- recent windows can flatter a candidate that loses to the actual live baseline

So the promotion rule is now:
- annual truth first
- walk-forward second
- portfolio compare third
