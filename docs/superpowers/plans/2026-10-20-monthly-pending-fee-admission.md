# Monthly pending-fee admission — approved PM continuation, ORDERS_OFF

Base:543c137. Implements the owner's20Oct directive and19Oct minimal CR.
No new strategy, ledger, financial permission, LIVE deployment or reserve amount.
Existing liability_reserve_usd is the single cash reserve; actual finality stays
strict. Pending accounting may support entry only with an explicit new owner-scope
term, replayed complete raw activities, matching owned fills/cash and known tariff.
Unknown/excess costs, stale evidence, foreign exposure or changed sources block.

## Native execution tasks

- [x] RED: incomplete trading day/late fees, partial fills, unknown fees and
  already-posted cents; default strict accounting remains blocked.
- [x] Add an explicit estimate mode to existing fee reconciliation/producer;
  preserve default finality output. Bound already executed account-day fees,
  subtract actual posted amounts, preserve PENDING and immutable provenance.
- [x] Bind admission to a fresh replayed estimate, exact book/account and the
  existing owner-pinned reserve. Deduct the account pending amount once from
  conservative loss admission, never turn it into final net PnL.
- [x] Refresh cost evidence after rotation and before each entry through the
  existing single Monthly manager. Keep protection/recovery outside this gate.
- [x] Run targeted fault/restart/late-posting tests and exact package checks;
  obtain one independent critical review and fix material findings.
- [x] Prepare the exact ORDERS_OFF server rehearsal/rollback and activation CR.
  Scope any remaining server/runtime acceptance honestly; do not activate LIVE.

NET: independent read-only opening check is separate; existing manager/monitor,
DAY policy, SHOP cancellation and all financial authority remain unchanged.

Ruling: pending estimates are not finalizer inputs. The new scope term must
explicitly authorize the changed admission, and old grants cannot opt in by
accident. Future/unknown charges are not guaranteed by the executed-fill estimate;
reserve adequacy and new LIVE use require the final owner-reviewed packet.

Local final package: bd267c75380f9bc8ad1f82175d89e963043ec6c4d561bb02a7e63f3d7bd74faa,
51 sources,274 exact PASS,39 imports,0 checkout fallback,network denied.
Independent narrow fix verification closed all4 findings (34 PASS,1 full E2E
excluded); final full E2E then passed in the exact suite. Server evidence and
the remaining production-entrypoint/handoff boundary are recorded in
reports/ALPACA_MONTHLY_PENDING_FEE_ADMISSION_2026_10_20.md.

Server exact274 PASS/39imports/0fallback,51source+18test hashes match;93protected
static pins unchanged. Candidate unselected,0real broker requests/writes. This
checkbox closes the bounded patch/rehearsal preparation; production applying
entrypoint, actual NET handoff and final financial packet remain explicitly OPEN.
