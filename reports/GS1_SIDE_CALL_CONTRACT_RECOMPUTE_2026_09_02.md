# GS1 side/caller-contract recompute — 2026-09-02

The side/call boundary repair is operational: the physically pre-cut GS1 run
completed **1,525,853 strategy calls with zero exceptions**. The output passport
is `complete`, so the previous empty passport was not caused by another hidden
caller failure.

This is a research-only result. It did not change live configuration, risk,
orders, positions, or money authority.

## Input integrity

The accepted recompute used a physical H1 snapshot ending before
`2025-10-01T00:00:00Z`: 137 files, 1,220,785 rows, 38 empty pre-cut files, zero
post-cut rows, and maximum timestamp `1759273200000`. A committed per-file
manifest binds the temporary execution snapshot.

The earlier corrected run over the full source directory was discarded for
promotion purposes. Although the runner applied a logical date mask, those NPZ
files physically contained post-cut rows. The accepted result below comes only
from the physical pre-cut snapshot.

## Gate result

Across the two windows (`2024-03..2025-09` and `2023-01..2024-02`):

- 209 configuration cells existed in both windows;
- 17 had positive net R in both windows;
- 13 also had at least 200 observations in both windows;
- 7 also exceeded the visibility/noise gate in at least one window;
- **0** also had a positive weekly-bootstrap lower bound in either window.

Verdict: `FAIL_CLOSED_NO_STRICT_GS1_CANDIDATE`. Interesting subgroups remain
hypotheses, not promotion candidates.

## PUMP-family boundary

The corpus audit found four symbol-first strategies: `pump_fade_simple`,
`pump_fade_v2`, `pump_fade_v4r`, and `pump_momentum_v1`. Explicit signature
dispatch now covers them in tests. The old `passport_pf.json` is empty and
predates that contract, so it is stale. PUMP4 is M5 logic and must be recomputed
through an M5-native runner; feeding it to this H1 GS1 machine would be a new
measurement defect.

Machine receipt:
`reports/receipts/GS1_SIDE_CALL_CONTRACT_RECOMPUTE_2026_09_02.json`.

Input manifest:
`reports/receipts/GS1_PRESEALED_INPUT_MANIFEST_2026_09_02.tsv`.
