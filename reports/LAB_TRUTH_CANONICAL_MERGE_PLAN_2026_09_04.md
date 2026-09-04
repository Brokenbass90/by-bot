# LAB_TRUTH canonical merge plan — 2026-09-04

## Outcome

Make the canonical research path refuse false multi-timeframe evidence while
preserving the already-verified strategy-call contract and explicit caller
diagnostics.  This is research-only work: no live configuration, orders, risk,
or money authority changes.

## Scoped acceptance sequence

1. Add focused tests for timeframe parsing, complete UTC aggregation, exclusion
   of an open higher-timeframe tail, symbol isolation, missing children, and
   unavailable lower timeframes.
2. Introduce one canonical mutable-prefix OHLCV store and make
   `research_machine.py` use it without weakening `build_ohlcv_caller` or
   `SignalCallDiagnostics`.
3. Prove the Store's closed-bar result matches the production closed-kline
   boundary when a raw exchange response contains a forming higher-TF candle.
4. Run direct strategy versus broker-free shadow-wrapper L1 parity for frozen
   ATT1 and ETS2S profiles, recording every no-signal and exception decision.
5. Run focused tests, research/caller contract tests, compile checks, an
   independent byte comparison, and a secret-aware staged diff review.
6. Commit and push only this verified canonical slice.  Claude's bulk WIP,
   generated data, backups, cleanup deletions, seal outputs, and candidate
   promotion files remain outside this commit until independently audited.

## Non-goals

- No parameter tuning or reinterpretation of ATT1/ETS2S results.
- No sealed-data opening.
- No deployment or canary authorization.
- No wholesale copy from `bybit-bot-clean-v28`.
- No migration of legacy one-off research scripts in this tranche; they are
  not the canonical `research_machine.Store` and must not be cited as evidence
  until migrated separately.
