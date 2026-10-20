# Independent whole-change review: Monthly pending-fee admission

2026-10-20. Reviewed uncommitted diff against BASE 543c137231e25731835b64b029d6a581669813f7, four production modules and new pending-fee tests. Verdict: CHANGES REQUIRED (three financial admission defects and one supported-source regression). This is code review of the candidate, not plan review or LIVE approval.

## Important findings

1. **P1 — Strict-success short circuit bypasses account liability classification.** `alpaca_monthly_native_binding_v1.py:282-288`: `_accounting_for_admission` returns `_accounting_net(), None` before inspecting current account. With no exits, or with all exits previously finalized, explicit pending mode accepts arbitrary new `accrued_fees`/`pending_reg_taf_fees`, including missing/invalid aliases. Reproduction: no exits plus accrued_fees=1000 returns `(Decimal('0'), None)` despite reserve .03. These liabilities may affect the new order's cash/loss admission. Repair: validate both aliases in explicit pending mode on every admission; nonzero liabilities require fresh classified account evidence, otherwise fail closed. Default strict path need not change. Zero/negative/nonfinite/missing aliases and all-final/no-exit cases need targeted tests.

2. **P1 — Fee model is self-pinned but not bound to owner-authorized LIVE scope.** `alpaca_monthly_cost_source_v1.py:205` and `alpaca_monthly_native_binding_v1.py:122-123`: input replay proves internal consistency, but the estimator accepts any freshly pinned protocol satisfying the structural contract. The new LIVE scope pins only policy and reserve, not the actual tariff. Replacing SEC rate with zero before generation yields an accepted lower pending bound (.01 instead of .02) and higher conservative net (1.99 instead of 1.98), without changing cash/fills. Before actual assessments arrive the mismatch cannot be caught by posted fees. Repair: the new owner scope must pin the exact approved protocol bytes SHA256; validate every pending document's protocol input SHA256 against that pin under LIVE custody. Missing/mismatched pin rejects. This concerns authorized source provenance, not cryptographic authentication of locally captured broker bytes.

3. **P1 — Evidence can age beyond the five-second bound during replay/final dispatch.** `alpaca_monthly_cost_source_v1.py:214-215`, `alpaca_monthly_native_binding_v1.py:450-458`: freshness uses `now_ms` captured before replay and source hashing; the final callback then checks current clock/window without rechecking evidence age. A delayed `_document` replay taking 5.1 seconds still admits an estimate whose cutoff was already one second old at call time (actual age >6 seconds). Repair: account for elapsed monotonic time when validating completed replay; return observed/cutoff timestamps in proof and recheck against the final effective time after the final clock GET immediately before POST. Preserve the reservation/no-resend behavior on failure. Test delayed replay and delayed final-clock separately.

4. **P2 — Exact book JSON comparison rejects expressly supported broker representation changes.** `alpaca_monthly_cost_source_v1.py:206-208`: producer refreshes order JSON after `execution_identity_v1` accepts added `source=access_key` and narrowly permitted timestamp rounding, then stores refreshed JSON in snapshot. Admission compares that snapshot to retained original book JSON literally. Reproduction: adding only `source=access_key` to get_order responses successfully produces pending evidence but admission raises `MONTHLY_PENDING_FEE_BOOK_CONFLICT`. Repair: preserve original book snapshot plus separate refreshed executions, or compare strict non-order structure plus existing `execution_identity_v1` for each raw_entry/exit order. Do not broadly normalize fields or weaken economic/book identity. Test metadata addition, microsecond rounding, and a truly material change rejection.

## Evidence and limits

`PYTHONPATH=.:tests .venv/bin/python .private/monthly_pending_fee_20261020/reproduce.py`

Observed output on reviewed candidate:

```
baseline ADMITTED net=1.98 pending=0.02 elapsed_seconds=0.0
liability ADMITTED net=0 pending=None elapsed_seconds=0.0
metadata BLOCKED ValueError MONTHLY_PENDING_FEE_BOOK_CONFLICT
tariff ADMITTED net=1.99 pending=0.01 elapsed_seconds=0.0
stale_during_replay ADMITTED net=1.98 pending=0.02 elapsed_seconds=5.11
```

`git diff --check` PASS. Reproductions use existing synthetic fixtures and isolated temporary directories; no tracked code or source pins modified, no broad suite, broker/VPS/network/credentials/judges invoked. System python lacked pytest; successful reproduction used the existing .venv. The tariff reproduction exercises the estimator in PAPER; applicability to LIVE follows the reviewed scope fields and absent protocol equality check. Staleness reproduction exercises actual replay delay, not a complete fake-broker POST. Root's focused regression results are external to this independent verification.

Positive scope checks: strict finality remains the default; pending documents retain a distinct schema and PENDING_NOT_FINAL; terminal finalizer replays strict generation; posted cents are subtracted before the pending bound; the bound is deducted once after summing pending/finalized exit nets; immutable inputs/source hash replay and foreign-fill/cash checks are retained; account lock remains the original lock; recovery/maintenance execute before accounting and reserved recovery bypasses new-entry admission. Main opening path refresh hook runs after rotation and before each new ticket; the new test asserts hook ordering only, not a full pending rotation plus multiple-entry wire lifecycle. Require focused integration evidence for that path before candidate acceptance.

No deployment, increased reserve, $4 allowance, final net PnL, or money authority is inferred from this review. No approved scope was created or changed.

## Narrow remediation verification — 2026-10-20

Scope: only the four findings above and their direct changes in `alpaca_monthly_native_binding_v1.py` / `alpaca_monthly_cost_source_v1.py`. No second whole-change review. The new `run_pending_rotation` rehearsal and `full_frozen` E2E case were explicitly excluded while the root agent continued developing them.

Result: **all four original findings CLOSED in the reviewed fixes**.

1. Liability bypass CLOSED: explicit pending mode validates both aliases and account/currency before consulting completed accounting; invalid/missing/negative/nonfinite aliases fail, and nonzero liability after strict-success raises UNCLASSIFIED. Existing strict default remains unchanged. Cases cover no exits and simulated all-final accounting.
2. Owner tariff binding CLOSED: LIVE custody requires a valid explicit protocol SHA256 in the owner scope, and pending admission compares it to the replay-verified protocol input's raw-file SHA256. Missing/mismatched authorization rejects. Ordinary PAPER fixtures intentionally remain usable without a LIVE grant.
3. Replay/final-clock freshness CLOSED: completed replay includes elapsed monotonic time; proof carries source observation/cutoff timestamps; final dispatch rechecks age after obtaining the final clock and before handing control to POST. Delayed replay and final-clock cases reject, with the latter preserving the durable reservation and producing no buy.
4. Supported representation regression CLOSED: book comparisons validate each raw entry/exit order with existing `execution_identity_v1`, then compare every non-order field exactly through canonical digest. Supported access_key and narrowly permitted microsecond rounding pass; existing book/source conflict tests continue to reject. No broad normalization was introduced.

Independent command executed:

```
.venv/bin/python -B -m pytest -q tests/test_alpaca_monthly_pending_fees_v1.py -k 'not full_frozen' --tb=short
34 passed, 1 deselected in 1.05s
```

No new material issue attributable directly to these four repairs was found in this bounded pass. No tracked files edited; no network, broker, VPS, credential access, broad suite or full E2E run. This closes the listed code-review defects only; it does not supply the pending full lifecycle/rehearsal acceptance, deployed runtime proof, reserve increase, owner LIVE GO, or final net PnL. Root reports model/effort runtime evidence is recorded separately in `model-runtime.json`; this pass did not independently inspect that metadata.
