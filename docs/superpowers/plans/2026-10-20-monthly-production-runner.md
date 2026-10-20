# Monthly production entrypoint — approved inline continuation

Base:230106b. Spec: owner's20Oct PM directive (Monthly + PUMP4 TINY), current
Monthly delivery and existing standing plan. Implement the missing thin entrypoint,
not a new strategy/framework. ORDERS_OFF staging only; no actual GO, broker writes,
NET/SHOP/units/HALT/lock edits or research changes. Existing recovery/manager/book
remain authoritative. Unrelated allowlist file is outside this change.

1. RED→GREEN: default/disabled CLI cannot load a profile or dispatch. Explicit
   dispatch requires a source-complete production spec, separately signed owner
   scope and exact runner config identity; old grants cannot activate it.
2. Wire existing MonthlyManager.tick + automatic capture/cost callback + existing
   restricted Monthly transport. Profile identity/lock checked, no env discovery
   or PAPER fallback. Source/accounting failures retain owned maintenance.
3. Test real entrypoint with memory-only transport: frozen58 source, restart/lost
   replies/late costs; no second manager/book. NET remains foreign and cannot be
   silently adopted; handoff/rollback reject exposure/uncertainty/pending cost.
4. One bounded independent critical review, targeted fixes; exact local/server
   ORDERS_OFF rehearsal, hashes/receipts, bounded standing dossier and commit.

Pre-flight: tick already owns dispatch.lock; callbacks run under cycle guard
before new entries. Cost producer uses original account lock. Entry-point config
must be owner-pinned separately from source bytes without a circular scope/spec
hash. Rule: runner_config_sha256 binds operational config excluding authority
paths; existing scope/GO bytes and implementation pins are validated separately.
Default remains the existing disabled source/preview interface. No wait for30Oct
for engineering; actual30Octsource/2Novfacts and financial owner GO remain future.

20Oct outcome: steps1–3 and the bounded entrypoint review/exact local+VPS
acceptance are complete (29same tests,52sources,5synthetic E2E receipts).
The source is staged UNSELECTED. Step4 financial standing dossier and actual
legacy handoff/rollback continuity remain OPEN, explicitly separate from this
component PASS. Next RED targets the entry-only legacy scheduler retirement
requirement; no old manager/timer has been retired and no GO has been issued.
