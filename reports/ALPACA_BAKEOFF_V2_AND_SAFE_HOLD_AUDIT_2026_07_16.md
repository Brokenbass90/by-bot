# Alpaca SAFE_HOLD + successor bake-off audit — 2026-07-16

Overall assessment: **research design ready; performance replay remains `BLOCKED_FAIL_CLOSED`; forced liquidation is not supported by current evidence.**

No broker call, order, sale, deployment, live-env change, outcome read, or performance calculation was made in this work.

## Live SAFE_HOLD finding

The latest local live mirror was authoritative as of `2026-07-16T04:02:03Z`:

- mode: `SAFE_HOLD`;
- positions: `ABBV, ABNB, GE, SCHW`;
- broker-side stop coverage: `4/4`;
- protection gaps: none;
- account equity: about `$486.34`; cash/buying power: about `$328.45`;
- manager receipt status: read-only/dry-run.

There is therefore no research or operational evidence for selling all four positions merely to restart a strategy. A forced liquidation would realize the current path, add execution risk, and still would not fix the research/live parity defects. The safe path is to let broker stops protect the existing holdings and keep the account in preservation mode until an exact successor passes.

`SAFE_HOLD` does **not** mean the sleeve has been abandoned. It means:

- `ALPACA_ALLOW_NEW_ENTRIES=0` — no replacement or new buys;
- `ALPACA_CLOSE_STALE_POSITIONS=0` — a freshly generated list cannot liquidate existing names;
- `MONTHLY_MIDMONTH_ROTATION=0` — no accidental daily/mid-month churn;
- broker protection and read-only manager verification continue.

An individual position may still leave via its protective order. A manual/forced sale becomes justifiable only for a separate operational emergency (account restriction, irreparable protection failure, invalid position ownership) or after an approved successor explicitly schedules the transition. Neither condition is present in the inspected mirror.

## Material parity defects found

The attractive historical v38 numbers were not produced by the same portfolio contract intended for live:

| Component | legacy research | intended live/successor |
|---|---:|---:|
| eligible universe | fixed modern ticker list | point-in-time membership required |
| target gross exposure | 100% normalized | 70% |
| universe top-k | 14 | 18 |
| earnings blackout | 5 days before / 2 after | 3 before / 1 after |
| sector cap | absent in legacy simulator | maximum 2 |
| sizing | score / ATR, normalized | score / sqrt(ATR), normalized |
| drawdown | monthly/rebalance endpoints | daily mark-to-market required |

Consequently, neither the old `+50–63%` reports nor the adaptive sparse-DD result can authorize live rotation. They remain useful diagnostics only.

## What was completed

A successor five-arm contract now separates one variable at a time:

1. `v38_successor_spy200_gated`;
2. `v38_successor_ungated_control`;
3. `adaptive_v1_spy200_gated`;
4. `adaptive_v1_ungated_control`;
5. `v38_legacy_native_reference` — diagnostic only, never winner-eligible.

The four eligible arms share:

- true calendar-month close signal and next-XNYS-open fill;
- completed bars only;
- 70% target sleeve exposure;
- the same 5/10 bps-per-side base/stress costs;
- the same stop, target, break-even, ATR trail, gap, ambiguity and max-hold logic;
- daily mark-to-market and initial-capital-inclusive drawdown.

The A/B validator proves that the gate comparisons change only the gate and selector comparisons change only the selector. A shared-object alias bug caught by the new test was fixed, so mutating one research arm cannot silently mutate its control.

## Future forward seal

The first honest successor window has been sealed **before** it starts:

- sealed: `2026-07-16T04:04:22Z`;
- start boundary: `2026-08-03` (exact session time must come from the pinned XNYS ledger);
- end boundary: `2026-11-04`;
- minimum: three complete monthly entry cycles;
- interim outcome reads: forbidden;
- parameter changes and automatic promotion: forbidden.

This fixes the old problem where the July 13 window was declared untouched after it had already begun. It does not authorize a performance run yet.

## Remaining blockers

Preflight source pins: `10/10 PASS`. Future seal: `PASS`. SAFE_HOLD semantics: `PASS`.

Five authoritative inputs remain unpinned:

1. XNYS session ledger;
2. point-in-time eligible universe;
3. point-in-time adjusted daily market-data manifest;
4. corporate-action and delisting ledger;
5. reconstructed broker lifecycle plus cost/slippage calibration.

Until all five pass, permission remains `BLOCKED_FAIL_CLOSED`, performance stays uncomputed, and SAFE_HOLD must remain.

## Next safe sequence

1. Materialize and hash-pin the five inputs without opening forward outcomes.
2. Implement one common portfolio runner using the already tested exact execution/exit primitives.
3. Run historical diagnostic/OOS comparisons only after preflight passes; do not tune on the sealed future window.
4. Journal the August–October forward cycles without interim reads.
5. After the full window, require parity review plus paper/live transition review; never automatically sell or promote.

## Evidence

- `backtest/alpaca_bakeoff_v2_contract.py`
- `scripts/preflight_alpaca_bakeoff_v2.py`
- `configs/preregistered/alpaca_bakeoff_v2_20260716.json`
- `configs/preregistered/alpaca_bakeoff_v2_forward_manifest_20260716.json`
- `reports/research/alpaca_bakeoff_v2_20260716/preflight_receipt.json`
- `tests/test_alpaca_bakeoff_v2_preflight.py`

Focused verification: `16 passed` across the new successor preflight, exact parity materialization, and the legacy adaptive diagnostic tests.

