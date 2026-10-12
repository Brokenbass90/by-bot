# Brain V2 V1.1/A7 — single authorized development run

**Terminal: `STOP_V1`, version `BRAIN_V2_V1_1_A7`. Permission spent.**
The frozen requirement was BRAIN_DET net USD ≥ FOUNDATION in at least three
of four folds, together with the DD_ENV bound. Actual: **one of four**, DD bound
PASS. Funding UNKNOWN is below 5% in every arm, so this is a completed negative
development result, rather than missing-data termination. No repeat or rescue.

## Authorization and identity

- Direct human reply: “Да — GO на один прогон Brain V1.1; LIVE остаётся HALTED”.
  [Owner receipt](evidence/brain_v2_v1_1_20261012/OWNER_AUTHORIZATION_20261012.json)
  records question `call_IIdNaE7EsMMbdNeP3EUFeIzi` and the original answer.
- Frozen research `36ab6ff29d32b73972f7e2996f2c40bd0c00a35b`; actual origin
  `4260cbc60b5b0f8cdf6d85d6d00338dfd006a5b5` had no Brain-file difference.
- Code/preparation `4bdb8ddd1bd1e2e2551a0428dce6d27a953de837` was pushed and
  remote-verified before any V1.1 outcome. Execution checkout HEAD `2a9c344`.
- Canonical manifest pin:
  `7f2968c722b4c1bc617c65e7c9f497fffc59108b1fa2318b7004ad33e5a5d60a`.
  This is the manifest-body identity, not its file-byte SHA.
- Fresh preflight returned `V11_PINS_VERIFIED_RUN_NOT_STARTED`; all five table
  pins and 215 original source files passed before the sole invocation.
- `STARTED`: **2026-10-12 15:10:16.738661 UTC**;
  `TERMINAL`: **15:10:46.341514 UTC**, exit 0, elapsed **29.603 s**.
- `filter_runs=1`, `run_permission_consumed=true`, `orders_allowed=false`,
  `money_authority=false`. Original V1 remains spent `BLOCKED_DATA`, unchanged.

## Frozen comparison

Continuous model E0 **$100,000**, test entries July 2023 through September 2025.
Percentages below are total model-period returns, not annualized or live returns.
R already contains 6 bps commission per side; separately charged 2 bps slippage
per side and source-bound signed Bybit funding under A3/A4/A6.

| Recorded metric | RAW_SAFE | FOUNDATION | BRAIN_DET |
|---|---:|---:|---:|
| Net model USD | +23,075.10 | −12,764.35 | −18,179.49 |
| Total return | +23.08% | −12.76% | −18.18% |
| Final realized model USD | 123,075.10 | 87,235.65 | 81,820.51 |
| PF, known-cost terminals | 1.0360 | 0.9732 | 0.9592 |
| Known-terminal expectancy USD | +5.48 | −3.54 | −4.82 |
| A5 DD_ENV | 24.55% | 29.33% | 29.94% |
| Realized DD, reference only | 20.37% | 25.44% | 26.37% |
| Accepted = closed | 4,287 | 3,662 | 3,830 |
| FUNDING_UNKNOWN | 77 / 1.80% | 60 / 1.64% | 58 / 1.51% |
| Scheduled occupied slot-hours | 209,762 | 186,371 | 194,502 |
| Round-trip known turnover USD | 68,379,564.23 | 48,647,787.53 | 45,043,200.44 |
| Commission already inside R, model USD | 41,027.74 | 29,188.67 | 27,025.92 |
| Extra slippage USD | 13,675.91 | 9,729.56 | 9,008.64 |
| Signed funding USD (negative = credit) | −6,451.16 | −2,628.52 | −3,552.48 |
| Maximum recorded Σnotional / realized E | 1.43769 | 1.38065 | 1.44156 |
| SF3 known net USD | −18,342.36 | −30,397.08 | −7,514.68 |

| Entry-time fold | FOUNDATION net USD | BRAIN_DET net USD | Noninferior |
|---|---:|---:|---|
| 2023-07 → 2024-01 | +1,705.47 | +847.65 | FAIL |
| 2024-01 → 2024-07 | +3,878.37 | +852.82 | FAIL |
| 2024-07 → 2025-01 | −7,686.76 | −15,249.84 | FAIL |
| 2025-01 → 2025-10 | −10,661.44 | −4,630.11 | PASS |

The DD_ENV ratio is about 1.02075, within 1.1. It does not override the failed
three-of-four criterion. DD_ENV is the frozen historical envelope, **not MTM**.
UNKNOWN-funding trades release risk on schedule and contribute no PnL to E or
metrics; absent funding is not zero. All remaining positions released by
**2025-10-01 00:45 UTC**, no entries after the exclusive October 1 boundary.

## A7 and recorded-evidence verification

**353** opportunities rejected before context/scoring/allocation in every arm:
ATT1 11, ETS2 57, SF3 283, BOUNCE1 2. All rejected rows have null context/z/risk/
table/priority; no accepted lev > 100. Per-fold counts are in the native receipt.
No clipping, new training, retuning, dropped sleeve or changed economic model.

[Native terminal](evidence/brain_v2_v1_1_20261012/run_v1_1/TERMINAL.json)
SHA `a27b7cb152bc5647194d17a105ff717e7b0ef932dc0b1352703dc9104a83d3fd`.
[ARTIFACTS](evidence/brain_v2_v1_1_20261012/run_v1_1/ARTIFACTS.json) pins all five
compressed journals, counts, canonical record chains and terminal digests.

[Post-run reconciliation](evidence/brain_v2_v1_1_20261012/POST_RUN_RECONCILIATION.json)
is `RECORDED_JOURNAL_CASH_AND_PINS_PASS`: **160,532 records**, **69,741** unique
opportunities, **79,012** continuous 15-minute ticks. Independent arithmetic
matches every saved cash/ENV/DD/risk/position tick, terminal cash, fold PnL,
costs, unknown counts, A7 rejections and final release tail. This reads recorded
decisions; it does not run an evaluator/allocator or generate another decision.
Original V1 receipt/journal hashes, source/table/code pins and foreign allowlist
SHA unchanged. Both authorized experiment versions have distinct spent markers.

[Descriptive trade diagnostics](evidence/brain_v2_v1_1_20261012/RECORDED_TRADE_DIAGNOSTICS.json)
preserve count, known net, UNKNOWN count, scheduled slot-hours and risk-dollar-
hours by sleeve/symbol/direction. No concentration statistic becomes a new gate.
Idle cash remains UNKNOWN: no frozen execution/margin model. Bootstrap interval
is NOT_COMPUTED: no frozen resampling unit/block/seed/interval rule was supplied;
no post-result method was invented. These report limitations do not rescue STOP.

Pre-run checks: 41 Brain targeted PASS; preceding combined preparation had 55
PASS including 14 liquidation checks. No implementation changed after outcomes.
Pre-start tests/CLI that assume the run directory is absent are not re-executed
after the spent run. Full suite historically not green, not rerun. No new
independent-review signoff; earlier reviewer allowance limitation remains.

## Operational consequence and next gate

V1.1 remains development evidence on already-consumed history. RAW_SAFE's positive
result and low PF do not prove independent net edge or actual-account feasibility.
Neither a failed Brain policy nor RAW_SAFE obtains live authority from this run.
Any later challenger needs a separate frozen design and explicit authorization;
there is no automatic retune/retry, B3 rerun, policy promotion or strategy revival.

**Zero broker/VPS/service operations in this authorization cycle.** Latest actual
NET PAPER evidence remains the dated October 12 capture, not a new readback here.
Alpaca P0 stays October 13 **13:30 UTC / 16:30 Cyprus** actual DAY re-arm if held,
then original scoped exit/cost/finality (unwind not before 13:35, hard end 14:00
UTC). No repeat entry/reprice/restart/extra PAPER statistics. LIVE HALT remains;
an exact LIVE dossier and separate owner GO are still required.

Liquidation source V2 stays **NOT_DEPLOYED**; old sources untouched. KITY independent
October 15/22 evidence schedule, ATT1 and Claude research remain unchanged.
