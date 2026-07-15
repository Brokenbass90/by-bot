# Claude Research Station v2 — preservation audit

**Status:** preserved as a diagnostic proposal generator; not promotion-grade and not a live component.

The completed `deeprun1` contains `107` unique trials: ATT1 36, regime level-fade 54, pump-fade 12, and one default run each for Elder, horizontal breakout, range scalp, impulse breakout and midterm v3. Only `impulse_breakout` passed the first in-sample gate. It then failed both the later-half forward gate and the OOS-symbol gate. Final survivors: `0`.

This is a useful negative result. It prevents us from treating the present parameter space as a source of a ready second sleeve. It does not prove that the strategy families can never work.

## Preserved source and evidence

- `research_lab/search_station.py`: SHA-256 `3c9f63440c332e125f673f73735c98e138b86768a11c9974ace1c47bda1ad79a`
- `research_lab/run_station.sh`: SHA-256 `b6c7905ace687adecea6c4878242f064adc479012453da8d0bbe8102a3d87785`
- `research_lab/README.md`: SHA-256 `eae8a011b1cdb8e1056a94e30070c5026c5db7fdaf57e91191a30cd1b0d2e83f`
- `research_lab/results/deeprun1.jsonl`: SHA-256 `363551e170a6dc30e3e185b9500f47caf2a73b506dd483e36e9b0c79ab91b1e0`; 107 rows and 107 unique trial keys.

## Why this runner cannot promote money

- It selects the largest mutable cache file per symbol instead of an immutable source manifest with common time boundaries.
- The same four OOS symbols become known after the first run and cannot remain a reusable untouched holdout.
- A per-symbol half split is based on row count, not one pinned shared UTC boundary.
- The fixed 107-trial result has no family-wise multiple-testing correction, trial ledger or deflated performance statistic.
- Failed forward/OOS reasons and full metrics are not retained in the existing result rows.
- Costs are generic and funding, liquidity, instrument metadata and portfolio timestamp occupancy are not frozen end to end.

## Allowed use

Use the station to propose a small number of new hypotheses. A proposal may advance only by receiving a new identity, frozen data/cost/execution contract and genuinely unseen validation before outcomes are viewed. Do not expand this mutable runner into thousands of variants and select a winner from the same forward/OOS cohorts.

The current safer successor path is Pattern Atlas -> one preregistered hypothesis -> separate parity scorer -> one sealed test -> prospective paper. The station remains available for ideation and resumable diagnostics.
