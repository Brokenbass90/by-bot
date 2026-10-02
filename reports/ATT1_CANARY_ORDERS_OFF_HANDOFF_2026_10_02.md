# NEW ATT1 orders-OFF — engineering delivery, October 2

Tasks1–4 are implemented in the existing recovery tree. **Engineering acceptance
PASS; actual account build readiness BLOCKED_ACTUAL_INPUTS_AND_COHORT.**
`SEND_ENABLED=False`, `orders_allowed=false`, `owner_go=false`; no money runner,
production install, DB migration or NEW order occurred. The accompanying JSON is
the reproducible readiness receipt; its observations retain their real timestamps.

## What exists

- Source-bound fixed USDT risk, notional≤100 and daily admission debit `D=2R`.
  Exact quantity/rounded stop and conservative fee/funding reserve bind to the
  captured command. Fresh OLD sizing requires all effective inputs and hashes;
  declarations establish consistency, not authentication. No guessed live cap.
- One existing FULL-synchronous SQLite ATT1 slot. `BEGIN IMMEDIATE` checks cash,
  occupied risk, exclusive NEW_READY route, actual drain declarations and imported
  OLD H1/cooldowns atomically. Missing migrated reserves mean unknown exposure.
  Full profile/intent/command persists before command exposure; restart returns
  the original link for lookup, never a new submission identity or automatic OLD resume.
- Entry preparation requires valid native pause, same-account flat/full pages,
  all OLD intents/costs final and all8 OLD symbol watermarks. Flat GET alone is
  insufficient. Late OLD fill returns to reconciliation/draining. Import cannot
  lower an existing cooldown. Fixed initial C is not advanced on every later entry.
- Protection and reduce-only exit preparation derives from the real existing
  LifecycleSession. It validates exact current coordinator intent/account/held
  remainder and leaves journal ACK/fill/protected state untouched. Entry-budget/
  pause/flat gates do not block owned management. Partial/acknowledged exit uses
  the existing stable lookup link; no new exit identity while status is unknown.
  Account fingerprint alone is insufficient to recreate UID-bound exit IDs:
  management evidence carries `reservation_account` and verifies its fingerprint.
- Budget-bound finality requires the owned recovered session matching saved
  profile, intent, command and execution binding. Complete source identities and
  exact lifecycle gross PnL, fees and signed funding must match terminal cash.
  Cash debit transfer, frontier and slot release share one transaction; boolean
  flags and a command tag alone cannot release the slot. Terminal evidence hash
  is retained in the existing table. No new ledger or journal writer.
- Daily spent cash never refills with profit/retry/restart. Outstanding reserves
  carry over midnight. Historical command cash, when explicitly source-covered,
  can reconcile delayed prior-day finality without charging it to today's budget;
  missing/conflicting source coverage blocks release. Prior-day completion hashes
  and complete OLD+NEW coverage remain required; dates do not prove settled costs.
- Dedicated deterministic34-file archive excludes the runnable OLD money bot,
  credentials, private evidence, DBs and unrelated files. It carries an AST-extracted
  inert seam, original monolith source hash, per-file hashes and a separate execution
  implementation pin. Numeric proposal/evidence is mode0600 outside the archive.
  Enabling the seam captures commands only and suppresses OLD fallback entry.
  No service/unit/activation script is installed by the builder.

## Verification and critical findings

Local242 focused tests PASS. Target233 tests PASS on VPS Python3.12.3 in a new
`/tmp/att1-canary-orders-off-*` tree, plus enabled-seam capture/recovery self-check.
Nine local packaging tests cover deterministic archive, missing caps/checks,
source/dependency mismatch, sendtrue/authority rejection and extraction/import.
The target bundle contains the full monolith solely as AST test input; it was
never imported or installed on the money service. First target attempt failed a
missing existing GET collector dependency; corrected closure was rerun successfully.

One independent `gpt-6-astra/high` critical review (`3caf369..83d2f0b`) found two
P1 bypasses: finality could zero real costs; direct reserve could omit handoff.
Both reproduced RED, then fixed in `3f999c9` and verified by primary regression
checks locally and on target. The independent review itself returned
CHANGES_REQUIRED; it was not repeated and is not retrospectively called PASS.

Historical pure receipt oracle:14 captured public sessions /162 records retain
byte-identical full receipt hashes and original journal hash chains. The repository
already had a broker-native-stop coordinator extension before this cycle, unlike
the deployed public closure. Direct reopening old public journals with this broker
candidate correctly refuses its different implementation pin. No header was
rewritten: public recovery uses the original deployed closure; new broker evidence
needs its own explicit implementation/epoch pin. Frozen public strategy/profile/
2s rules and deployed public source were not changed here.

The full repository suite retains57 preexisting failures. Exact failed node IDs
and comparison against the pre-implementation baseline are in the readiness JSON;
this delivery does not claim a globally green repository. No sealed evaluator or
research outcome window was consumed to fix historical tests. Existing watcher
tests appended fixture rows to the actual untracked local allowlist log; those
own rows were archived privately and removed only after verifying the exact
original prefix/hash. Original bytes are restored. Future full suites must
redirect watcher CHANGE_LOG/RESTART_FLAG to temporary test files.

## Remaining actual-account inputs

Before an actual BUILD_READY_ORDERS_OFF receipt, collect one bounded signed GET/
source packet using the selected existing account/client:

1. Complete effective OLD sizing calculation: selected account/equity, effective
   percentage, strategy/breaker/volatility factors, reserve/leverage/slot/notional
   constraints, deployed source and effective configuration hashes. Propose fixed
   private numeric R≤that budget and D=2R; no increase with equity.
2. Source-proven account fee tier and conservative funding cost reserve, with
   full OLD+NEW UTC cash attribution, fees/funding publication/finality and
   historical carry. Breaker net PnL and an empty current positions endpoint are
   insufficient. Archive original signed response bytes privately.
3. Full OLD outstanding-intent inventory/finality and exact8-symbol consumed-H1,
   cooldown/last-terminal watermarks from actual runtime sources. The OLD native
   pause is already applied; do not reapply it or invent watermarks from wall clock.
4. Bind authentic packet to the accepted source/target hashes and independent
   review/fix receipt. The builder validates declarations and hashes; the trusted
   collector and owning review prove their provenance.

No new real money until2–3 **prospective filled clean terminals with terminal
net-R** under the unchanged2s evidence, fresh OLD comparison/exclusive dossier and
separate owner GO. Clean execution alone does not prove positive net edge.

## Exact rollback/handoff boundaries

**This preparation cycle:** all changes are local/Git; the VPS received only an
isolated offline acceptance tree. No code rollback is needed on bybot/public/
Alpaca. Keep OLD entry pause and its running management. Keep public evidence and
all released package/receipt hashes. Reject failed or changed inputs explicitly;
never fall back to an OLD entry.

**Before future money activation:** repeat fresh broker truth and late-fill
checks, prove OLD intents drained, import watermarks conservatively and choose C
strictly after drain/last OLD H1/preparation. Exactly one entry owner. Review the
future selected-client dispatch separately; no canary flag here creates that runner.

**After any future real NEW fill:** suspend NEW admission while the same owner
continues protection, reduce-only exits, signed GET recovery and costs/finality.
An uncertain order retains the slot and stable link. Never switch back to OLD
or discard DB/journal state over NEW/unknown exposure. Any manual financial action
requires the owner's separate authority.

## Next work, without expanding this delivery

Alpaca remains P0; next regular-open DAY transition October5. Public NEW continues
prospective collection while actual input collection closes the next canary blocker.
Regime/Elder is a separate preregistered availability/baseline comparison; no LIVE
filter change. Claude's current KARTA/research ref outranks old handoffs: NOCHNOY
FX is now KILLED/NOT_EXECUTABLE, PM2 awaits frozen verdict, TOLPA forward first
needs PIT refresh. Factory work follows one accepted end-to-end experiment and
current defect evidence, not a broad rewrite. See CURRENT_PROJECT_ROADMAP.md.
