# L3 accounting core — 2026-09-07

Status: `LOCAL_SYNTHETIC_CORE_REVIEWED`. The preceding L3 implementation step
is complete for synthetic arithmetic. Full strategy execution/accounting parity
and real net edge remain unproven. No deployed runtime was changed.

## Delivered and verified

`research_lab/att1_ets2s_accounting.py` implements a pure short linear-USDT
ledger with exact Fraction arithmetic over bounded decimal inputs. It tracks
remaining cost basis, realized/unrealized PnL, per-execution signed fees/rebates,
settled funding, fixed initial risk and closed net-R. Unknown fees or incomplete
funding evidence suppress net outputs. Late entries preserve actual exposure
and cannot rewrite prior realized PnL or reset finalized R0.

Independent fixtures include gross +10 with fees .19 => net 9.81 and .981R;
gross +10 with fees 11 => net -1; signed funding, rebates, partial exits and
interleaved entries. Positive synthetic arithmetic is not a profitable strategy.

The critical review caught duplicate funding timestamps under different IDs:
cash could be counted twice while set-based coverage passed. This is fixed,
with regressions. Exact redelivery remains idempotent. Synthetic profile IDs
are enforced. Financial review found no unresolved blocker for this slice.

Verification on 2026-09-07:

```text
.venv/bin/python -m pytest -q tests/test_att1_ets2s_lifecycle.py tests/test_att1_ets2s_accounting.py
42 passed in 0.26s (23 L2 + 19 L3; final integration rerun)
```

Independent review additionally checked 1,500 event prefixes for cash
conservation and nonretroactive realized PnL. The earlier unchanged L1/evaluator
suite passed 134 tests on September 6; it was not rerun as a 176-test command.
Hashes and preserved review:
`research_lab/results/att1_ets2s_l3_core_20260907/local_verification.json`.

## Next bounded P0

Bind the full ATT1 execution profile and causal admission to the L2/L3 cores,
then add priced stop/target/protection and restart reconciliation fixtures plus
an independent comparator. Recover ETS2S wait-clock and full BE/target semantics
before its profile can pass. Execution identity must distinguish delivery
metadata from stable fills; fee/funding source hashes need real evidence, not
only syntactically valid synthetic provenance.

The unchanged L1 burn-in is `IN_PROGRESS`: 53/53 required cycles, 5,402 journal
rows and 30 raw signals across the whole journal at 2026-09-07 12:27:18.120 UTC.
No findings. Receipt:
`research_lab/results/att1_ets2s_burnin_20260907/onsite_receipt_20260907T122718Z.json`.
Full burn-in evaluation remains no earlier than September 8, 08:02 UTC.

After full L2/L3 evidence, a new clean zero-risk lifecycle is required before
an owner-approved money canary. Calendar time or these unit fixtures grant no
money authority.
