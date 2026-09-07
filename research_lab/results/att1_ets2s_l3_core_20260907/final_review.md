# Final financial/state review — synthetic L3 arithmetic

Status: **PASS for the bounded synthetic slice; no unresolved blocker found**.
The initial funding blocker below was corrected and independently rechecked.
This review covers the
pure synthetic reducer only; it does not establish actual fees/funding coverage,
instrument parity, L2/L3 integration, or any promotion/money authority.

## Initial blocker — resolved

**P1: distinct settlement IDs at one scheduled timestamp doubled funding while
coverage remained complete.** Initially, `att1_ets2s_accounting.py:353-358`
adds every unseen settlement ID to cash; lines 366-371 compare timestamp sets,
which erase multiplicity. Repro: short 1@100 at t100; final at t102 with stop110;
funding `f1/s1` at t110, qty1, mark100, rate.001; another `f2/s2` with the same
timestamp and economics; exit1@90 at t120; complete schedule `(110,)` covering
[100,120]. One receipt yields funding=1/10 and netR=101/100. Both yield
funding=1/5 and netR=51/50, with coverage=true and no issues.

The fix rejects a second distinct settlement at the same timestamp before cash
is added. Independent replay of the original repro now raises
`AccountingViolation`. Exact original and alias redelivery after exit remain
no-ops: funding=1/10, closedR=101/100, coverage=true. Regression tests cover the
collision and idempotence. A `SYNTHETIC_` profile-prefix guard was also added;
independent checks reject live, unqualified and lowercase profile names.

## Verified behavior

- Focused suite: initially **17 passed**, after correction **19 passed**
  (`.venv/bin/python -m pytest -q tests/test_att1_ets2s_accounting.py`).
- Independent deterministic review of **1,500 event prefixes** passed exact
  Fraction cash conservation: gross+unrealized equals entry proceeds minus exit
  payments minus held quantity times mark; fee-adjusted equity, aggregate entry
  totals, and nonretroactivity of prior realized PnL also matched.
- Partial exits preserve remaining weighted cost; later entries add only their
  own cost. Finalized R0 stays fixed through partial exits and unexpected entry.
  A late entry followed by complete close retains `FINAL_ENTRY_DRIFT` and no R.
- Exact old event/execution aliases do not rewind clocks. Changed execution
  payload, unseen clock reversal and overexit reject. No-final, zero-R0 and
  unknown-fee cases suppress closed R. The supplied suite verifies signed fees,
  signed funding, missing/extra coverage, and Decimal-context independence.

## Future adapter requirements, not proof from this slice

Bind profile/instrument/currency, original accepted stop, execution identifiers,
liquidity and fee provenance to real immutable receipts. The enforced synthetic
profile namespace is a useful scope guard; a string/hash alone does not prove
provenance. Normalize redelivery timestamps before this strict payload-identity
API; explicitly resolve corrections, out-of-order receipts and same-timestamp
causality. Supply authoritative settlement schedules, complete coverage,
settlement quantities and any required zero-held observations. Reconcile real
cash/fees/funding and L2 lifecycle finality before claiming full L3 parity.
