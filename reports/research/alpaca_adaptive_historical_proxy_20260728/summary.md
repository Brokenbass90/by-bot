# Alpaca Adaptive V1 historical proxy — verdict

Date: 2026-07-28  
Stage: `RESEARCH_ONLY / REPAIR`  
SAFE_HOLD: unchanged

## Outcome

Waiting for several forward months is no longer the first diagnostic step.  The
current selector was replayed causally on the two available historical caches:
selection uses only completed closes, entry is the next observed session open,
and every position uses the frozen shared stop/target/break-even/trailing
contract.

At 5 bps per side:

| window | gated return | ungated control | gated PF | gated DD* | red months |
|---|---:|---:|---:|---:|---:|
| 2022 bear survivor proxy | -1.61% | -8.70% | 0.648 | 2.43% | 2/11 |
| 2025-2026 recent survivor proxy | -3.58% | -7.28% | 0.838 | 9.21% | 5/11 |

`*` DD is measured on monthly endpoints in this proxy, not promotion-grade
daily portfolio MTM.

The market gate is useful: it materially reduces losses and drawdown in both
windows.  The complete current model is nevertheless unprofitable, so the
historical verdict is not a delayed PASS; it is a concrete `REPAIR`.

## Failure localization

The shared exit produced:

- bear window: 9 stop exits and 2 targets across 11 trades;
- recent window: 24 stop exits, 7 targets and 1 max-hold exit across 32 trades.

This makes the next bounded experiment an exit-attribution A/B: unchanged
selector with shared exit versus calendar hold and wider risk-preserving exit.
If calendar hold remains negative, selection must change.  If calendar hold is
positive while the shared exit is negative, the execution/exit contract is the
binding defect.

## What this proves and does not prove

It proves that the current Adaptive V1 should not be promoted merely because
the forward ledger is slow.  It also proves that the SPY gate contributes real
defence in both tested windows.

It does not prove a final no-edge verdict because both universes contain current
survivors, the calendar is inferred from observed SPY sessions, the sample is
small and broker lifecycle is not calibrated.  Massive Basic PIT materialization
and an authoritative XNYS ledger remain required before any capital decision.

## Reproduction

```bash
.venv/bin/python scripts/audit_alpaca_adaptive_historical_proxy.py
```
