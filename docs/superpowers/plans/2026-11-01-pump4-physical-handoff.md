# PUMP4 physical source-repair handoff — approved-scope implementation plan

Continue aef951d. Reader05f89618/194files/210tests is accepted unchanged; do not
reimplement it or touch Monthly/Claude. User requests complete offline installer,
final independent acceptance, key-lifetime plan, then exact owner packet. No GO
for financial selection or extension has been granted.

## Rulings

- Ruling: finish installer offline BEFORE key-lifetime solution. The earlier
  handoff's ONLY-after wording applies to activation/GO readiness, not safe
  preparation. Otherwise an external key action unnecessarily stalls engineering.
- Ruling: propose a separate one-entry pilot 1Nov19:26:32.774UTC–8Nov19:26:32.774UTC,
  <=7days, unchanged50/30/20/risk1/max1entry+position, not TINY2 serial authority.
  This is a PROPOSAL requiring a new exact owner GO. No extension is performed.
- Ruling: keep original DATA/financial source epoch. New financial validity is
  an explicit scope, not re-timestamped data or replayed old activation.
- Ruling: install only after old financial root is wholly unused. Any admission,
  barrier, attempt, risk or flow history blocks migration even when broker flat.
  No spent-state reset/copy. Old scope/GO/history remain intact plus entry revoke.
- Ruling: pinned original account UID identity must match the fresh selected key;
  key fingerprint can change only through separately pinned credential source /
  original-owner snapshot in exact new envelope. No active .env replacement.
- Ruling: key must cover latestentry+168h+24h reconciliation margin. A query-api
  documented no-fixed-expiry sentinel is accepted only with exact VPS IP binding.
  A finite validUntil is checked directly; no assumption any key is permanent.
- Ruling: after any new-owner start attempt, ambiguity is readback-only. Never
  retry or automatically roll back a possibly trading new owner. Revoke-entry
  rollback preserves selected custody. Before new start, restore old owner with
  entries durably revoked if a stopped handoff fails. Never clear claim/revocation.

## Steps and gates

- [x] RED workflow tests: missing GO/default no requests, key gap/UID mismatch,
  spent/raced history, lease contention, partial CAS/daemon/start failure,
  correct single transition and no repeated activation, revoke preserves custody.
- [x] Implement ONE packet installer using existing selected unit/original lock,
  existing safe file/lease helpers, GET-only sources, existing health observer.
  No order API calls in installer; default/verify-only cannot grant authority.
- [x] Complete offline health draft: partial/finalization is PENDING_SOURCE,
  completed verified source or protected custody distinguished; no normal pending
  spam. Test generated health and exact packet/config/unit closure.
- [x] Build immutable final v5 packet; independent Astra/high final review once of new
  installer + health + prior two fixes (do not repeat whole prior audits/suites).
- [x] Targeted local/VPS network-denied acceptance, actual GET verify-only on VPS,
  preserve old financial/DATA/Monthly units and histories. Same real-source
  coverage candidate, no broker writes/GO/stop/start.
- [x] Publish report/evidence/checkpoint. READY_FOR_OWNER_GO only if exact key,
  source, offline handoff acceptance and independent review pass. Otherwise name
  precise blockers, never hand owner an unready executable command.

Future operational checks: after19:26:32UTC fresh pilot readback (existing monitor),
Monthly2Nov14:30UTC conditionalBUY/CASH. Never claim these future checks completed.

Completion1Nov17:30UTC: engineering/publication package complete; see reports/PUMP4_PHYSICAL_HANDOFF_ACCEPTANCE_2026_11_01.md. Actual verify-only BLOCKED_PREFLIGHT solely KEY_EXPIRES_DURING_CUSTODY. READY_FOR_OWNER_GO remains false; key action, fresh verify, separate GO and future operational checks are not completed by these checked engineering tasks.
