# ATT1/ETS2S L2 exposure core — 2026-09-06

## Current status

The synthetic exposure core is reviewed and tested locally:
`LOCAL_SYNTHETIC_EXPOSURE_CORE_REVIEWED` with 23 focused tests passing. This is one bounded reducer slice, not full
L2/L3 execution parity and not a promotion or profitability result.

The reducer covers partial entry and protective exits, late fill finality,
duplicate and conflicting execution handling, causal ordering, exact quantity
conservation, and the `.3 -> .1 + .2` step-`.1` dust fixture. Decimal input is
bounded to 128 characters, 64 coefficient digits, and absolute exponent 64.
`terminal_eligible` means exposure-only reducer finality.

The critical review found no blockers for this slice. The implementation is synthetic-only and authority-free: no network, broker,
subprocess, filesystem, L1, profile inference, cash, persistence, or live
imports/calls. Parent integration checks also passed.

## Exact verification

```text
.venv/bin/python -m pytest -q tests/test_att1_ets2s_lifecycle.py
23 passed in 0.07s
.venv/bin/python -m py_compile research_lab/att1_ets2s_lifecycle.py
exit 0
```

The separate evaluator/release suite independently passed 134 tests in 24.93s
(34 evaluator plus 100 existing L1/release/Store). The combined evidence count
is therefore 157 across two separately executed suites; there was no single
157-test command.

## Pending gates

Before any money decision, bind production ATT1 and ETS2S profiles, including
the ETS2S clock and BE geometry; verify admission/dedup and causal observations;
implement priced triggers, order states, protection incidents, persistence and
restart reconciliation; complete the L3 ledger and an independent comparator;
then produce a clean zero-risk lifecycle receipt. No full profile, L2/L3 parity,
or money gate is claimed here.

The later transport adapter must normalize stable execution identity separately
from delivery metadata: the current fingerprint includes `received_ms` and the
original quantity text, so changed delivery metadata conflicts until an
explicit adapter policy exists. Full broker-redelivery parity is not claimed.

Source, test, plan, review, receipt and payload hashes are recorded in
`research_lab/results/att1_ets2s_l2_core_20260906/local_verification.json`.
