# October17 owner decisions — operational delivery

The owner forwarded the four written decisions in research7b3bfff. Actual origin
`research/fabrika-v1` and the local research ref both resolve to
`7b3bfff1bee58919ed792b181138c0a36f7150fb`. This supersedes the earlier
"NET exit is only a research proposal" status. No new monthly-money GO exists.

## KITY — exactly one new batch execution micro

One new policy **a1c97e6b94e3d1a1c8927e7dba252cbd12a1c6f49012133587a85c27fb8845c8**.
Valid only October17, through21:00UTC / October18 00:00Cyprus, no date transfer.
Price-free ten-symbol/five-long/five-short basket and existing quantity rules;
one post-GO capture,215USDT gross,50bps collar,CTS<=2s,60s entry deadline,
15USDT immediate all-in exit trigger with accepted overshoot, native Full stops,
30min from first durable intent, no averaging/scaling/re-entry/retry.
Execution-only; no KITY/C1-C3/edge inference or strategy-canary authorization.

The existing unit remains on its original ORDERS_OFF config. A separate inert
money config/unit and new immutable policy are staged, not selected or claimed.
Personal handoff verifies current pins/healthy idle state/flat account, stops
the SAME unit under the original lease, selects the new pinned config, confirms
healthy/private-WS readiness, then queues one exact batch GO immediately.
The GO clock starts after this static handoff. No report/rehearsal after GO.
Existing writer owns the entire lifecycle and finality. After the queue
uncertainty barrier, never rollback/resend/guess a command did not arrive.

Personal command, **one time only**:

```bash
bash /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/kity_batch_owner_20261017/owner-batch-micro-once.sh
```

The agent did not run it or enable monetary authority. No re-approval of the
already-given scope is requested; the personal command initiates the financial
action. If response is unclear, read receipts; do not run again.

Manifest SHA256 `4b525b2c36c4f069ff83ed0b2b5ad76fe0c094855bfaebf5e87a2d26d596872d`.
New inactive config SHA256 `3f107a63afd91d6db61f8cb0f2dfcb1807264e458827980f482ecb52b12e7960`.
54 targeted PASS (8 new helper tests, existing service/batch cases); no broad
suite rerun or actual monetary attempt. Source/readback/test evidence is in
`evidence/owner_decisions_20261017/`. No actual10/10 PASS from preparation.

## NET — November2 owned legacy exit

Owner authorized planned exit of ONLY original NET entry705a1b5b…d78d, at most
the remaining0.325167779, unless already stopped. OFF_PROTOCOL remains excluded
from monthly edge evidence. No stop widening, new entry or migration.

One actual Alpaca calendar GET verified November2 open **14:30UTC /16:30Cyprus**,
not13:30UTC. The corresponding original monthly rotation window is14:30–14:35UTC.
NYSE regular opening is09:30NewYork; timezone conversion uses IANA zones.
[NYSE hours](https://www.nyse.com/trade/hours-calendars).

Prepared separate source-pinned personal exit wrapper, **not armed**:
`/opt/bybot-research/alpaca-dynamic-live-20261013/legacy-exit-20261102`.
Manifest SHA256 `d6fe5870b30ddfb64b9874e0c97788f00e40152d90700279eae9b25729c21b58`.
It checks actual calendar/open clock, original account/entry/intake/remaining
quantity, retains the existing shared lock and invokes only the repaired
runtime's owned unwind. It cannot buy, clear HALT, widen a stop or adopt a new
monthly NET position. If original NET already exited and no NET order remains,
it records no-order flat observation; accounting finality is not inferred.
Any partial/unknown exit remains under original durable recovery; no blind resend.

Personal command is prepared for **November2 window only**, not today:

```bash
bash /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/net_rotation_20261102/owner-net-exit-nov02-once.sh
```

No financial timer or automatic order was armed. One app heartbeat
`net-2-preflight` is scheduled for November2 16:20 local Cyprus: READ-ONLY
preflight/reminder, never execution of this command. It expires after its one
check and does not transfer the date. Mac/app availability is not guaranteed.

69 targeted PASS (7 wrapper cases plus existing runtime tests). Money branch
was not run against the broker. Exact future source/account state remains a
fresh prerequisite; code changes before November2 must not be silently adopted.
Current NET stop/manager, monthlyV3/HALT and DAY monitor were not changed.

## Other two decisions / monthly activation

IBIT/ETF_PREMIYA and Farside remain Claude's public-data tasks. Research7b3bfff
is already on origin; Codex did not restart storozh or change Claude's checkout.
No research/judge/outcome run was performed. DAY monitoring is already active
GET-only (f7d3145); the research checklist's old unscheduled status is stale.
First actual regular-session protection confirmation remains October19.

Monthly equity-money activation still needs the separate November1 owner GO
and existing October30 source/selection/manager/ownership prerequisites. The
legacy NET exit does not authorize any monthly buy. Do not confuse a scheduled
read-only reminder with an armed financial exit or activation of monthlyV3.
