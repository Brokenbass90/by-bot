# KITY physical owner app v1.2 / health custody v1.3 — operator runbook

CURRENT subsequent bounded-pricing version: read
`KITY_BOUNDED_RUNTIME_2026_10_15.md`. Owner PID2186777/NRestarts0/ORDERS_OFF,
app-v2-bounded, config-v2-bounded.json36f3d72e…2269f,
unitf89b633b…8aeca, same lockinode818853. Original V1 plan/GO/DB and source kit
are retained unchanged.10/10actual GET-only rehearsal PASS,239targetedPASS.
New exact intent GO remains separate/pending; old ffebGO stays consumed.
**Never invoke the old rollback below for a selected V2 experiment.** V2's
explicit operator rollback resolves the selected journal before any restoration.
The remaining text is V1/health-v1.3 history, superseded for current commands,
config/unit identity and selected-experiment recovery only.

Current13:39:48UTC monitoring rebind: PID2182409/NRestarts0, config1699930e…1d7f2,
unit88ef47e4…1be7d, cronf01f0d95…507cd. Only one watchdog line changed; the
14 trading sources and all policy/bounds are unchanged. New monitor is read-only,
no restart/order authority, with complete-rollback legacy observation support.
Read KITY_OWNER_HEALTH_2026_10_15.md and evidence/kity_owner_health_20261015.
Earlier physical v1.2 receipt is immutable history, not current config authority.

CURRENT subsequent exactGO for ffeb4bc4…6570 was received and consumed once.
Runtime now retains actual GO/plan/journal, mode EXACT_GO_SCOPED_MANAGEMENT,
phase TERMINAL, verdict NO_SEND_NOT_LIFECYCLE_PASS,0POST/fills. Fixed IOC limit
became unmarketable; independent complete flat/open/history/execution readback0.
Do not prepare/GO another plan in this one-experiment runtime, reset/delete state
or reuse the spent GO. The generic command documentation below is retained for
operator reference, not permission to retry. Owned recovery/rollback remains
available under the existing safeguards.
Use this existing owner; never start another credential-bearing sender. Current
source receipt: `evidence/kity_micro_handoff_20261015/package_manifest.json`.
Old bybot/web are deliberately inhibited; original ATT1 admission/risk/source,
Alpaca HALT and all unrelated cron remain unchanged.

The exact ten-name list is specific to this execution experiment. No research
judge or policy promotion is part of these commands. Read the current physical
receipt and account state; a dated dossier is not a fresh quote.

## Fresh preparation (no money authority)

On VPS, from `/opt/bybot-research/kity-micro-owner-20261015/app-v1-2`:

```bash
/root/by-bot/.venv/bin/python -B -m research_lab.kity_micro_supervisor_v1 \
  --config /opt/bybot-research/kity-micro-owner-20261015/runtime/config-v1-3-health.json \
  --config-sha256 1699930e80fc314612388867761d3eed6241cd46de1b5e2ddfeed894d5b1d7f2 \
  --command '{"kind":"PREPARE"}'
```

Read the returned result file after the service finishes that command. Do not
resend an interrupted/claimed command: its receipt is `CONTROL_INTERRUPTED_NOT_RETRIED`.
Review `runtime/prepared/<plan_id>.json`: all10 exact orders/qty/IOC limits/stops,
215gross,15trigger/overshoot,30min,≤20.3% rounding, actual permissions/mode/free
funding and forecast costs; compare current source/custody. No preview creates
an actual lifecycle journal or monetary permit.

A no-send rehearsal is queued through the same command interface with
`{"kind":"REHEARSE","plan_id":"<exact prepared id>"}`. It does not send even with
all fresh gates PASS. Saved IOC prices can become unmarketable; rejection is
FRESH_ONLY. No reprice, automatic replay or repeat entry is authorized.

## Exact money GO — CONSUMED / DO NOT REPEAT

Show the human the exact fresh proposal. Only a direct human reply
`GO KITY_EXECUTION_MICRO_LIVE <exact plan_id>` authorizes submitting the following
control request with that same ID/text:

```json
{"kind":"GO","plan_id":"<exact prepared id>","exact_go":"GO KITY_EXECUTION_MICRO_LIVE <exact prepared id>"}
```

Use the existing client `--command` interface above. Never manufacture this
request from the handoff/install approval or a manager's recommendation. The
service verifies the source binding and fresh account flatness/funding, creates
one immutable active plan/journal/GO, then performs fresh per-entry gates and a
durable intent before its single signed POST. One experiment only; no automatic
new plan/re-entry/scaling. Fixed IOC limits are not changed after GO. An entry
rejected before any send ends NO_SEND; that is not an execution lifecycle PASS.

## Observe / recover / kill

Read `runtime/heartbeat.json`, `runtime/results/`, retained `runtime/raw/`,
`runtime/wire/` and the durable `runtime/lifecycle.sqlite` via the reviewed
journal interface. Do not edit/copy over/delete state. ACK is not fill/protection.
Unknown send/cancel requires actual realtime+history+execution readback; no
resend. Per-leg failures must not suppress other proven owned exits. Native
Full SLs and the portfolio monitor supplement each other. No foreign position
or order may be adopted or flattened.

The $15 all-in threshold or 30min deadline causes immediate scoped unwind when
observed; exchange/network/gaps can cause overshoot. Duration anchors at first
durable entry intent and cannot restart/extend. Restart inhibits further entry
and recovers/unwinds only proven owned exposure. Missing/corrupt existing
journal or GO proof is explicit failure, never a new empty ledger. Stop the
experiment with the same control interface:

```json
{"kind":"KILL","plan_id":"<active exact id>"}
```

This uses the existing scoped safety authority. Never kill the service while
exposure/dispatch/protection is uncertain. A post failure is not proof of no
order; keep recovery ownership. Actual transaction rows must reconcile every
owned execution/fee/funding settlement before final net accounting; missing
publication remains explicit pending. A known rejected exit requires owner
attention, not blind repeated submissions.

## Return to original owner

Only after no owned/uncertain/native risk remains and actual account flat/open
orders readback is complete:

```bash
/root/by-bot/.venv/bin/python -B -m research_lab.kity_micro_handoff_v1 \
  --config /opt/bybot-research/kity-micro-owner-20261015/runtime/config-v1-3-health.json \
  --config-sha256 1699930e80fc314612388867761d3eed6241cd46de1b5e2ddfeed894d5b1d7f2 \
  --action rollback
```

This persists an entry fence, checks the journal/unknown sends/native orders,
gets fresh flat sources, stops only this owner, verifies flat again, then removes
only its exact two inhibitor files/marker and restores the original bybot/web
units. It preserves all evidence/source versions. It is prepared and locally
tested at its safety guards; an actual restore was not performed in the
orders-OFF readiness task. Never manually start old writers while this owner
has exposure or any uncertain send. Posted accounting status remains explicit.

Alpaca Oct15 opening has priority; this KITY account/lock/GO cannot authorize or
alter Alpaca. KITY C1–C3/research ledger never consumes micro-experiment PnL.
