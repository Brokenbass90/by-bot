# Alpaca Dynamic LIVE — October13 preparation and existing PAPER postcheck

Status: **LOCAL_PREPARATION_PASS / ACTUAL_LIFECYCLE_PENDING / ORDERS_OFF**.
This is preparation, not PAPER_EXECUTION_PASS, an installed runtime, a completed
production handoff or READY_FOR_LIVE_GO. No monetary owner GO has been received.

The isolated runtime delivered October12 is reused. The October13 owner choice
adds an optional bounded first-entry intent beside the original exact-plan GO.
It approves implementation, not a purchase. No Brain/Factory/crypto work or
additional PAPER/statistical gate was introduced.

## Actual sources — separately dated

October13 **06:29:37.500 UTC /09:29 Cyprus** authenticated GET/state capture:
LIVE flat, open orders0, HALT, cash496.12; NET PAPER still0.325167779, original
DAY stop expired without a fill. Original guard PID1979385/NRestarts0 waits for
the next regular session. Original81 app pins and production PIDs/NRestarts
unchanged. Capture SHA
`e53e60e841f838a6fa58b79c328997488b3bf28046ed38685e95e3c1101759f0`.

Separate **06:52:42.704 UTC** read-only writer/profile/cron inventory SHA
`6aadd0f1fea685d95c7850bfaa86c93c03f3ed4c9549769d18280b99bc419e96`:
old writer/cron pins match the original arming source, old monthly entries are
OFF, only the NET guard is an active Alpaca process. New LIVE base is absent.
Original lock is `/root/by-bot/runtime/locks/alpaca_bridge_0d0c322aef55c952.lock`.
The native old management cron remains scheduled every five minutes; this is
not a completed exclusive new-manager handoff. Its proposed successor draft
uses that same cadence. Both captures made zero broker/server writes or lock
acquisitions. Raw broker/profile evidence remains private.

Afternoon actual re-arm, owned exit and finality are **NOT_DUE**, not inferred
from the morning snapshot or tests.

## Delivered implementation

`research_lab/alpaca_live_readiness_v1.py` and
`scripts/prepare_alpaca_live_readiness_v1.py` provide:

- A37-file credential-free app package, dependency/source closure and disabled
  entry/manager service drafts. No env files, owner permit, system unit install,
  timer activation, HALT clear or broker action is packaged as an executed step.
- Offline postcheck for the original actual PAPER lifecycle: account/app/policy
  pins, re-arm/remaining native protection, real STOP/MARKET fills, ownership,
  persistent retirement, recovery and complete source-bound cash/cost closure.
  A full rearmed stop that fills before the first snapshot is accepted only
  through its exact broker fill and retained native reconciliation. No active
  order or flatness alone substitutes for that proof.
- Conditional byte-verifying installation under only
  `/opt/bybot-research/alpaca-dynamic-live-20261013`, after actual PAPER PASS and
  the original14:05UTC postcheck. Repeat verifies; partial/drifted installation
  blocks without overwriting. No `/etc`, profiles, cron, old runtime or NET guard
  writes. Separate unapproved activation drafts are inert files.
- Exact-plan and pre-entry bounded dossier generators. Physical sources, an
  independent LIVE book, actual PAPER PASS and disabled-deployment readback must
  exist. Input-provided declarations are not authenticated by their hashes.

`research_lab/alpaca_dynamic_first_intent_v1.py` and the existing runtime's
optional `--first-intent` implement the owner's selected first-entry contract:
one exact ticker/session/ranking/OLD slot, fixed maximum qty/notional/stop risk
within frozen policy, an exact maximum limit price, original opening window,
one entry attempt and no transfer/reprice/repeat. Original native bridge, stop
manager code and static custody are pinned before the fresh opening plan.
The unchanged planner must fit every bound or reject; it cannot enlarge them.
This does not authorize later replacements or waive any original fresh gate.

The concrete dossier can be prepared before opening with fresh dated sources.
Its quantity is a maximum, not a reservation or a claim about a future fill.
The owner must separately approve its exact intent hash:
`GO ALPACA_DYNAMIC_FIRST_INTENT_V1 <intent_sha256>`.
No permission file is generated automatically. Missing GO/HALT/changed source/
outside-bound price or quantity means no entry. The original exact-plan permit
path stays the default when `--first-intent` is absent.

## PAPER cost closure — existing gate, correct source semantics

[Official Alpaca PAPER documentation](https://docs.alpaca.markets/us/docs/paper-trading)
states that regulatory fees are excluded from PAPER simulation. Archived
Markdown SHA is
`d43c9e2bdc1c4c9be8296a2a0b7b012441e6d293a44ea0d5c767d56d9709ade7`.
The existing personal commission-free account attestation/protocol remains
SHA `800ac28c805fec1ed01927edc63bae1696f66eff368a6ebe6ec5281c1d517a2c`.

These sources plus actual complete cash activities can close PAPER simulated
costs. Empty fees or pending0 alone cannot. The Oct11 cash-before source is
99410.28; the final activity query therefore starts Oct11, not Oct12. The new
GET-only `capture_oct13_finality_v2.py` preserves its pinned parent reader and
only widens that activity cutoff. Truncation, unpriced movement or cash conflict
blocks. USD-cent broker reconciliation is explicit. PAPER regulatory0 proves
nothing about future LIVE fees; CAT/SEC/reserves and LIVE finality stay unchanged.

## Existing October13 execution schedule — unchanged

The already-running server guard, not this observer, owns re-arm/exit:

1. 13:30UTC /16:30 Cyprus: real DAY re-arm if still held.
2. 13:32UTC /16:32: one original read-only broker/state capture.
3. Not before13:35UTC /16:35: existing scoped owned unwind; hard end14:00UTC.
4. 14:05UTC /17:05: one GET-only complete activity/finality capture and offline
  postcheck. No opener rerun, rescan, reprice, reservation or extra PAPER cycle.

For the original first observation, use the already-published reader with a
new private output:

```bash
.venv/bin/python reports/evidence/alpaca_net_paper_20261012/capture_post_attempt.py \
  .private/alpaca_net_paper_20261012/rearm_oct13_1332.json
```

Only after14:05UTC use the reviewed full-coverage reader:

```bash
.venv/bin/python reports/evidence/alpaca_live_readiness_20261013/capture_oct13_finality_v2.py \
  .private/alpaca_live_readiness_20261013/finality_oct13_1405.json
.venv/bin/python scripts/prepare_alpaca_live_readiness_v1.py postcheck \
  --arm reports/evidence/alpaca_net_arm_20261011/arming_receipt.json \
  --initial-receipt reports/evidence/alpaca_net_paper_20261012/post_attempt_receipt.json \
  --initial-capture .private/alpaca_net_paper_20261012/post_window_1335.json \
  --rearm-capture .private/alpaca_net_paper_20261012/rearm_oct13_1332.json \
  --terminal-capture .private/alpaca_live_readiness_20261013/finality_oct13_1405.json \
  --cash-before-capture .private/alpaca_net_arm_20261011/postarm_source.json \
  --paper-document .private/alpaca_live_readiness_20261013/paper_trading.md \
  --commission-protocol reports/evidence/alpaca_b3_gate_closure_20261008/alpaca_protocol_contract.json \
  --cost-closure-output .private/alpaca_live_readiness_20261013/paper_cost_closure.json \
  --paper-receipt-output .private/alpaca_live_readiness_20261013/paper_lifecycle_final.json \
  --output .private/alpaca_live_readiness_20261013/postcheck.json
```

Without a bound deployment/intake, the public result remains BLOCKED_DATA even
if the separate internal PAPER receipt is PASS. Do not mistake this for another
PAPER requirement. Following an actual PASS, the already-authorized disabled
installation helper is:

```bash
.venv/bin/python reports/evidence/alpaca_live_readiness_20261013/install_disabled_on_vps.py \
  .private/alpaca_live_readiness_20261013/disabled_package_v1.json \
  .private/alpaca_live_readiness_20261013/paper_lifecycle_final.json \
  .private/alpaca_live_readiness_20261013/disabled_deployment_capture.json
```

The package/hash manifest is in `evidence/alpaca_live_readiness_20261013/`;
private package bytes are frozen. Rebuilding changed code is a different package.
The helper refuses registered new units, never starts a service and returns a
physical deployment receipt. This command has **not been executed** this morning.

Next bind real authority/OLD terminal/cost sources and the distinct LIVE source
book. Keep the existing shared lock, retire competing entry/manager authority
through the reviewed handoff and preserve position management. Do not fake
`single_manager_verified` while old/new writers conflict. No profile/cron/unit
handoff has happened in this morning preparation. These are the existing source
and execution requirements, not a new statistical gate.

The `prepare-first-intent` command accepts `--spec`, `--binding`, `--preparation`,
`--paper-receipt`, `--deployment`, `--intent-output` and `--output`. Its spec lists
the function's exact ticker/session/ranking/slot/distance/maxqty/notional/risk/
limit/source-CTS/prepared-time fields. Preparation retains physically pinned raw
account/quote/asset/eligibility sources. It writes an intent only for a sourced
READY_FOR_LIVE_GO dossier; separate owner GO and authorized activation follow.
No new source construction is permitted inside the opening critical path.
Run production custody/dossier verification from the installed VPS app with its
actual VPS paths; local fixture/import tests cannot verify remote files. The
remote deployment receipt is retained at the new base's
`disabled_install_receipt.json`; bind the actual PAPER receipt separately as a
pinned source, rather than using an install helper's transport wrapper as one.

## Verification and practical limits

**194 targeted PASS**, including57 new readiness/intent cases. Package37files
verified, isolated app import/source closure and byte-accurate repeat install
tested locally. Original readback and inert install query compiled; actual
afternoon query and VPS installation NOT_RUN. Exact test/source pins are in
`preparation_receipt.json`, `test_receipt.json` and `package_manifest.json`.

Root review only; prior independent review allowance restriction retained, no
replacement/retry or independent signoff claim. No broad suite rerun: the prior
4560PASS/60FAIL suite/classification remains dated, NOT_GREEN; this does not
upgrade unrelated failures to a new money blocker. Foreign allowlist preserved
SHA `add587f1bd7059c2c706f1f7c604e36c2fb7b36b258b127e01fcd2101d3f19a1`.

Current caps487.42/gross0.70/max4/one inherited slot and native stop logic
unchanged. Tests use simulated broker evidence, not an actual LIVE lifecycle or
profit proof. Actual first-entry ticker/quantity/price/dossier/GO are not yet
available. Earliest next calendar openOct14 remains conditional on the existing
closures, fresh gates and separate owner approval. No promised execution date,
extra PAPER day, Brain rescue or KITY/ATT1/Claude change.
