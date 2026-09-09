# ATT1 handoff preparation and watchdog incident — September 9

`READY FOR OWNER ACTIVATION = FALSE`.

The immediate operational blocker is **recurring VPS lifecycle discontinuity**:
OLD watchdog restarted twice and both observed public v2 sessions have
`RECOVERY_GAP`. A clean prospective lifecycle gate is not met. Stabilize this
within the current runtime before any money promotion.

The next implementation work remains the **authenticated production OLD→NEW
dispatch/send/reconciliation path**: `smart_pump_reversal_bot.py` does not yet
call the durable routing functions or execute NEW coordinator intents. A tested
preparation ledger is not an installed no-duplicate guarantee. There is no
valid owner activation command to run at this checkpoint.

## What changed in this cycle

Extended the existing `bot/att1_coordinator_adapter.py`; no new trading daemon,
strategy, replay engine or core was added. The functions use tables intended
for the existing trade SQLite database, but were exercised only on fixtures.
No production database migration, OLD route pause or money operation occurred.

- Durable `OLD → OLD_PAUSED → NEW_READY` preparation states. `NEW_READY` is
  inert and grants no transport/money authority; `SEND_ENABLED` remains false.
- Cross-profile decision identity: account + ATT1 + symbol + canonical short
  side + closed H1; deterministic client order identity.
- One occupied ATT1 reservation per account, enforced by a SQLite unique index.
  State checks and mutation share `BEGIN IMMEDIATE`, with `synchronous=FULL`.
- Unknown send result has no TTL release. Restart preserves its occupied slot.
  Late ACK can bind after pause; conflicting/cross-account identity is refused.
- Cutover must be a future aligned H1 after the persisted OLD watermark and
  reported drain. Reservations must be final; known per-symbol 8h cooldowns
  survive the route transition. Existing uninstrumented OLD history is **not**
  automatically imported or considered covered by these new tables.
- Slot finalization requires caller-reported flat/order-final/complete-cost
  flags. These are validated inputs, **not authenticated broker proof**.
  Production reconciliation must establish them before this API is wired.

The draft worker implementation had cursor, transaction-order, identity and
clock-validation defects. Regression tests exposed them before the fixes.
The primary agent reviewed and corrected the code. Worker runtime metadata and
both relevant `turn_context` entries confirm `gpt-5.6-luna`, effort `medium`;
the worker later hit an allowance limit. No expensive replacement was spawned.

## Verification

Focused ATT1 suite: **192 passed**. The 25 new ledger tests include independent
concurrent DB connections, abrupt child-process exit after intent commit,
unknown ACK after restart, OLD/NEW exclusion in the ledger, retained cooldown,
missing/corrupt routing, invalid clocks, and incomplete finality/costs.

```sh
.venv-research/bin/python -m pytest -q \
  tests/test_att1_exclusive_reservation.py \
  tests/test_att1_lifecycle_*.py \
  tests/test_att1_ets2s_lifecycle.py tests/test_att1_ets2s_accounting.py \
  tests/test_verify_att1_lifecycle.py tests/test_att1_broker*.py
```

Target Python **3.12.3**: the same **25 tests passed**, in an isolated temporary
directory at low CPU priority. Dependencies came from the existing public v2
application. No dependency install, credential loading, broker request or
service restart was involved. Exact files executed:

| File | SHA-256 |
|---|---|
| `bot/att1_coordinator_adapter.py` | `f9f7503aa7d77136d6a5551057690c59d4e3c809ccdba079b7af1847a6e4eeda` |
| `tests/test_att1_exclusive_reservation.py` | `fa04aa13418fd7f52eaedc04f5c3e79eeb507c00dd9744fc9a07a0b141f0833c` |

Target execution is a fixture smoke, not a deployment or production handoff
test. The earlier public v2 restart/burn-in receipts remain separate evidence.

## Confirmed watchdog incident

On September 9 at **16:02 UTC / 19:02 Cyprus**, the external watchdog observed
a heartbeat age of 96 seconds, above its 90-second limit. Its log records an
allowed restart with reason `stale_heartbeat_age_96s`; systemd records a clean
stop/start at **16:02:11 UTC**, producing OLD PID `1160394`.

The VPS itself had not rebooted (host uptime around 210 days). The kernel
journal in the incident window contained no OOM event. Systemd does not show an
application crash at that boundary. `NRestarts=0` does not contradict the
external `systemctl restart` recorded by the watchdog.

At 16:04 the watchdog reported heartbeat age 3 seconds. Its subsequent sampled
entries through 16:58 remained OK. After-first-restart signed
GET reconciliation at **16:50:56.977 UTC** returned **zero open positions and
zero open orders**, with complete pagination and unchanged PID during collection.
This is current broker flatness at that timestamp, not reconstruction of every
event at the incident instant.

At **17:02:03.630 UTC**, a new read-only snapshot measured heartbeat age **146s**.
The watchdog independently recorded **145s**, then issued a second restart;
systemd start is **17:02:15 UTC**, new OLD PID **1206069**. At 17:03:09 its
heartbeat age was approximately 10 seconds. This recurrence supersedes any
assumption that the first successful restart had resolved the incident.
Fresh signed GET at **17:05:40.115 UTC** again proved zero open positions and
orders, complete pagination and unchanged PID; heartbeat age was **9.1s**.

The same second snapshot measured load **6.91** on **one vCPU**. Existing `sar`
history confirms only **0.34% CPU idle** in the 16:00–16:10 interval and swap
activity averaging **545.55 pages/s in, 598.05 pages/s out**. At 17:00 sar
recorded a run queue of 20. Multiple cron tasks and shadow runs overlap around
the hour. These observations establish resource pressure, not attribution to
one job. Read-only inspection also finds synchronous signal/kline work inside
the OLD async entry path and synchronous health work before heartbeat writes.
**The specific stalling call/root cause is NOT_CONFIRMED**: no timed Python
stack was captured; `py-spy` is not installed. Do not claim one shadow caused it.

Public v2 at 17:02 had **two sessions, CRVUSDT and DOGEUSDT**, both with
`RECOVERY_GAP`, flat simulated exposure and **null final net-R**. `poll_errors`
was empty; that does not clear lifecycle incidents. These are dirty prospective
observations, not two clean finished trades. Preserve their journals and the
2s continuity threshold. The correlation with OLD hourly stalls is unproven.

No watchdog threshold, money configuration, service priority or background
schedule was changed. Do not mask the incident by extending the heartbeat or
continuity limits, and do not alter another owner's Alpaca/strategy jobs.

## Exact continuation, without a new architecture

Work only in the existing ATT1 dispatch, guarded order submit, startup recovery
and coordinator adapter. Connect the durable owner check before scheduling and
before sending; commit the account-wide decision reservation before a possible
send; reconcile by stable order identity before any retry or release. Import
the actual OLD watermark/cooldown and pending-intent truth before a cutover.
Do not add a second independently credentialed ATT1 service or OLD fallback.

Within that same binding, obtain the OLD process's effective risk inputs,
including its runtime capital override/equity cache, and bind the pinned risk
and daily cost budget to authenticated broker/account truth. Config files,
startup multiplier and a fresh wallet balance alone do not prove exact OLD
absolute risk: the current heartbeat omits those in-memory inputs.

All activation gates in the existing migration plan still apply, including
protection/exit/cost reconciliation and clean prospective evidence. Do not mark
them passed merely because reservation tests pass. OLD money, public v1/v2 and
L1 remain as deployed; other strategies and research remain outside this cycle.

Raw signed account snapshots, application log tails, exact account economics
and smoke transport script/output are retained under ignored local
`.private/att1_handoff_20260909/`. They are not published to the public origin.
