# ATT1 continuation — September 9

**DEPLOYED ZERO-RISK V2 + RESTART PASS. READY FOR OWNER ACTIVATION = FALSE.**

Public v2 source commit: `8e3b122c926cb0e5f0227ad26f4d40c53b5ce94d`.
32-file closure: `a759f1d6dddb7f8e790fb09144d4acff6763ff6ecdd88efb46debd44bbf279a1`.
Frozen strategy profile remains
`79d23e38a6bb851fb7e300c2e0d0c22b48b671585d4c060eb5384c192b128050`.

## Completed engineering

The public driver prioritizes held/pending exposure and defers H1 scans and
funding requests while observation is required. Funding is reconciled after
closure through the existing delayed-settlement path; open costs remain
unverified. Completed flat funding coverage is checked before any repeat GET.
A slow orderbook response is checked after receipt as well as before the call;
the receive clock of a gap event is pinned to that observation. The 2s threshold
and dirty-incident semantics are unchanged. Scan coverage can be deferred while
occupied; that is visible missing observation, not a fabricated no-signal result.

The retained old public journal establishes a post-entry polling gap, but has no
phase timings to identify which historical scan/funding/publication/host delay
caused it. No claim of precise historical attribution is made. Original v1 keeps
its source binding and journals; its incidents are not cleared or reclassified.

The existing profile, L2, coordinator, L3 and durable session now support an
explicit `BROKER_REPLAY_ATT1_V1` binding with all authority flags false. It binds
declared account/source hashes and owner-provided limits to the frozen strategy.
Quantity is floored after reserving allowable adverse entry risk and notional
up to the original stop. Venue minimums reject rather than increase quantity.
Actual entry risk/notional breaches enter the existing incident path.

The transport-free `bot/att1_coordinator_adapter.py` maps broker-shaped execution,
terminal-order, conditional-protection and funding records into coordinator
events. It rejects foreign order/symbol identities, unsupported fees/modes,
missing execution reconciliation and unproven protection. ACK and pending cancel
are not terminal evidence. Signed funding cash is retained exactly, including
broker rounding, historical quantity, delayed delivery and boundary uncertainty.
The funding sign follows the official [Bybit transaction-log contract](https://bybit-exchange.github.io/docs/v5/account/transaction-log).

These are read-only replay capabilities, **not a connected live adapter**. Hashes
do not authenticate supplied records. Receipt evidence is explicitly
`BROKER_REPLAY_INPUTS_NOT_AUTHENTICATED`; actual account costs remain unverified.
There is no transport, send method or production OLD/NEW routing change.
Max-one/daily-limit binding fields constrain declared configuration only; the
account-wide durable reservation and daily admission ledger are not yet wired.

## Verification and deployment

- 167 related tests PASS, including exact funding credit/debit, conflicting
  redelivery, missing coverage, protection/finality mismatches, cap breaches and
  durable broker-shaped replay. All financial fixture values are synthetic.
- All 23 original synthetic event-prefix receipts and four public-runtime
  restart-stage receipts remain identical to the September 8 evidence.
- Target Python 3.12.3: full standalone verifier JSON equals local JSON, all
  archive hashes and public preflight PASS. No target dependency installation.
- Unit: `att1-lifecycle-zero-risk-v2.service`, user `bybot-research`, public GET
  only, no credentials/private API/order calls, 160MiB/30% CPU limits.
- App: `/opt/bybot-research/att1-lifecycle-zero-risk-v2/app`.
  Runtime: `/opt/bybot-research/att1-lifecycle-zero-risk-v2/runtime/v2`.
- Actual controlled restart: PID `1035462 -> 1035554`, state SHA
  `d78253fc59a23e79697a6c70ba2a806c223dfc837eee658f2f90212100d67942`
  identical before/after and equal to startup restoration.
  **There were zero prospective sessions at this restart.**
- Separately on VPS, a writer and independent reader reproduced all 23 isolated
  nonzero-exposure fixture prefixes, costs and net-R exactly. No test trade was
  injected into the prospective runtime. Four public endpoint GET probes PASS.
- OLD live and original v1 PIDs, units and v1 deployed files remained identical
  across deployment. L1 source/config/units remained identical. Rollback affects
  only the new v2 unit; retain its journals and release files.

Evidence: `research_lab/results/att1_lifecycle_v2_20260909/` contains the package,
target smoke, deployment, restart and exact executed payload receipts. The broker
adapter is not included in the 32-file public-runtime package.

Final read-only snapshot at 12:01:10 UTC: v2 PID1035554, NRestarts0, ~21.7MB
memory, 4 prospective symbols scanned/4 public GETs, no poll errors, zero
sessions, zero broker/order calls. This is startup observation, not a completed
prospective cohort. OLD remains PID3514874 and v1 PID68289; both active.

L1 final verdict remains the already completed `PASS_OPERATIONAL_BURN_IN`, 72/72
required slots, zero missing. Do not rerun the closed evaluator or treat its raw
signals as trades/net edge.

## Current next gate

Production OLD-to-NEW exclusivity is the next engineering blocker. Implement the
approved pause/drain/fresh-H1 cutover in the existing bybot dispatch, persistent
decision consumption and account-wide reservation, deterministic order lookup on
uncertain send, carried cooldown and daily costs/risk reservation. Prove crash,
late-fill, concurrent-symbol and restart cases before any possible activation.
Do not add a second credentialed trading daemon. Never fall back to OLD on NEW
errors. Continue management of existing positions while admission is closed.

Fresh fully bound OLD absolute risk, authenticated broker evidence/protection
binding and a clean prospective v2 lifecycle remain activation prerequisites.
The September 9 06:33 UTC private direct snapshot was flat/orders-empty, complete
pagination, OLD active; breaker state had changed from the previous snapshot.
It is a dated snapshot, not a currently fixed risk guarantee. The capital override,
equity cache and old fallback/rounding observability caveats still apply. Private
broker snapshots stay under ignored `.private/` and the local private archive.

No owner money activation is requested by this report. NEW send is unavailable.
Other strategies and LAB_AI implementation remain paused under current ATT1 scope.
The deterministic laboratory is being used for replay, costs and recovery tests;
an autonomous LAB_AI worker is not claimed to be running.

Mechanical implementation used Terra/medium, verified against thread metadata
and actual `turn_context`. The worker's last turn hit its allowance limit; root
completed verification and critical review. There is no independent final-review
PASS and no measured allowance-saving percentage.
