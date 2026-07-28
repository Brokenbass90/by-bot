# XSEC V4 family landscape — independent receipt

Date: 2026-07-28  
Stage: `RESEARCH_ONLY`  
Capital: forbidden

## Outcome

Claude's proposed cheap falsification test did **not** kill XSEC.  The fixed
36-variant neighbouring family was positive in all 36 configurations after the
same 15 bps cost contract:

- mean compounded return: `+40.32%`;
- median compounded return: `+35.86%`;
- minimum / maximum: `+9.82% / +87.75%`;
- positive configurations: `36/36`;
- median annualized Sharpe: `2.11`;
- published V4 champion: `+49.07%`, annualized Sharpe `2.77`, DD `6.89%`,
  `4/4` positive time folds;
- champion percentile inside the fixed family: `75%`, not an isolated maximum.

The published champion also reproduces the earlier `+49.1% / Sharpe 2.73 /
DD 6.8%` headline closely enough to establish implementation parity for this
diagnostic.

## Decision

`PIT_WORK_JUSTIFIED`, not `LIVE`.

The result is broad enough that rebuilding the universe point-in-time is worth
the engineering cost.  It rejects the narrow hypothesis that V4 was merely one
positive point surrounded by a zero-centred family.

It does **not** reject survivorship bias: every variant uses the same locally
available survivor-only data.  It also does not measure funding, real
slippage, partial fills or exchange execution parity.  Therefore no annual
return forecast and no capital promotion follows from the `+35.86%` family
median.

## Validation report

Overall assessment: **Share with caveats**.

Calculation spot-checks:

- the grid contains exactly `3 × 3 × 2 × 2 = 36` preregistered variants;
- the receipt contains 36 evaluated rows and 36 positive returns;
- the champion row is fixed by the published parameters, not selected again;
- `n_trials_effective_independent` remains `null`, because neighbouring
  configurations share data and cannot honestly be called independent;
- input and preregistration SHA-256 hashes are stored in `receipt.json`.

Binding capital blockers:

1. point-in-time universe with launch/delisting history is absent;
2. no independent untouched OOS;
3. funding is absent from the return ledger;
4. slippage and fill quality are unmeasured;
5. target-weight to executable-order parity is not proven.

## Reproduction

```bash
.venv/bin/python scripts/audit_xsec_v4_family_landscape.py
```

Artifacts:

- `configs/preregistered/xsec_v4_family_landscape_20260728.json`;
- `reports/research/xsec_v4_family_landscape_20260728/variants.csv`;
- `reports/research/xsec_v4_family_landscape_20260728/receipt.json`.
