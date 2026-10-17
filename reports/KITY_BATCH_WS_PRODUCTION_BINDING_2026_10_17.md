# KITY batch/private WS — production binding, October 17

**KITY_BATCH_WS_PRODUCTION_BOUND_ORDERS_OFF.** The existing production unit
now uses the batch/private-WS entrypoint. This supersedes the earlier
service-binding-pending status in KITY_BATCH_WS_ORDERS_OFF_2026_10_17.md.
There is no new money policy, financial authorization or actual ten-fill PASS.

## Actual deployment and readback

Same `kity-execution-micro-owner.service`, MainPID2440673, NRestarts0,
HEALTHY / ORDERS_OFF / NO_ACTIVE_PLAN, error=null. Private socket authenticated
and subscribed. Original account lock inode818853 is retained; a second lease
was refused. No second account writer was installed.

- App: `/opt/bybot-research/kity-micro-owner-20261015/app-batch-ws-20261017-v1`.
- Runtime: original custody root's `batch-ws-20261017-v1` child.
- Config SHA256: `4fd3634a70676306349fc7233c25eda784d9ceedc2ffc84c227f9e4571fe459f`.
- Unit SHA256: `ab0a4f8fbb19fb7f824ad3b08fb343d72212bc7b3a7f42aaa3be97586b8082f2`.
- Independent readback verified23 selected files and155 guard pins.

Fresh authenticated GETs before handoff, while quiescent and after startup all
reported positions0 / openorders0. Old source/history,34 previous wire records,
inhibitors, unrelated units and original lock were preserved. All95 Alpaca DAY
protection pins remained unchanged. The same health observer reads the stable
custody heartbeat; the retired bybot writer/watchdog was not resurrected.

Rollback source/config/unit are retained. Rollback requires actual flat state,
no uncertain/new send and no KITY exposure; it was reviewed, not fault-injected.

## Actual nonmonetary PREPARE

One `PREPARE_BATCH`, command1792225500587902567, completed at1792225512085ms UTC:
gross **207.953940 USDT**, `fresh_only=[]`, `OBSERVED_COMMON_2S_PASS`.
Result SHA256 `58f8220e6d32aed2491c2ab1f711a4d11fc6edc514ba2c71a954a42d9b2327dd`.
This is a dated account/source/sizing observation, not a durable fresh trading
permission. It created **zero policies, zero entry intents, zero broker POSTs**.

`money_go=false`; no selection or new wire exists. The disabled PREPARE path
cannot mint a permit or consume a policy. Old GO/expired9051 cannot activate
the new control namespace. Future money activation requires a new pinned
configuration/session and newly dated batch policy, then the human's personal
exact GO. No owner money command was run by the agent.

## Source and safety integration

`research_lab/kity_batch_service_v1.py` binds the existing BatchJournal,
BatchPhysicalOwner, BatchRuntime, signed GET/POST and private inbox to the
original lease. No second sender. Restart recovers durable owned state into
no-reentry reconciliation/unwind; absent selection with send history blocks.
Private ping continues during owned management. A socket failure does not
replace REST finality or stop scoped protection/recovery.

Ten entry intents remain one atomic journal transaction before one batch call.
The shared65-route fresh view avoids the former repeated per-leg GET path.
Existing native protection, partial/unknown recovery,15USDT immediate exit
trigger with accepted overshoot,30min lifecycle,215gross,50bps collar,
CTS<=2s and no averaging/re-entry remain. The new namespace uses60s; the old
one-policy70s approval is not transferred or silently extended.

## Verification and limits

**173 targeted PASS**, including13 service tests plus160 existing batch/WS,
account, physical ownership, runtime, native protection and integration cases.
Exact command and source/log hashes: `evidence/kity_batch_service_20261017/verification.json`.
RED evidence is retained privately. Root performed the bounded final review;
no replacement subagent or broad-suite rerun. Historical60 suite failures remain
unresolved; this report does not declare that suite green.

Actual batch orders/fills/protection timing have **not** been exercised in this
delivery. Engineering binding is complete, but **KITY_10_OF_10_EXECUTION_PASS
is still absent**. A future financial attempt needs a separate owner decision;
no research gate, policy/risk increase or extra PAPER cycle was added.

Evidence: `evidence/kity_batch_service_20261017/{installation,readback,verification}.json`.
