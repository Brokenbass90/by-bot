# Alpaca independent PASS, current NET and DAY next step — October 17

CURRENT: **ALPACA_STRATEGY_PARITY_PASS**, independently issued by Claude in
research commit `507f782` for recovery `d205f8f`. This is accepted parity of the
monthly/daily strategy, sizing and serializer, not financial activation.
[Exact review provenance](evidence/alpaca_day_protection_20261017/independent_parity_pass.json).

The reviewed 32-file V3 candidate remains unchanged, disabled and without a
bound monetary sender. Entry HALT remains. Existing NET is not migrated.

## What Monday does and does not mean

Actual bounded GET observation at **2026-10-17 06:28:39.330 UTC**:

- NET still open, quantity `0.325167779`.
- Open orders zero; last owned DAY stop expired.
- Broker clock closed, calendar empty for Saturday; next regular opening is
  **October 19 13:30 UTC / 16:30 Cyprus**.
- Existing manager timer active; last service execution exit0/Result=success.
- 56 source pins verified, ledger unchanged, original entry HALT unchanged.
- No order, manager restart, stop change, service mutation or financial action.

[Sanitized actual readback](evidence/alpaca_day_protection_20261017/current_readback.json).
This is not a claim that protection currently exists, or that Monday re-arm has
already passed. The manager must re-arm and confirm the owned full stop when
the regular session opens. Existing below-floor/protection-failure safety paths
remain the manager's authority; the observer does not create another writer.

The current manager has no configured forced Monday exit in its maintenance
path. A stop, existing safety exit or separate owner-approved close may end NET.
Calling the trade off-protocol does not itself authorize selling it. The new
monthly strategy neither automatically closes nor adopts NET.

The selected reference runs month-end selection then next-session entry.
Its next calendar opportunity is **October 30 close → November 2 09:30 New York /
16:30 Cyprus**, subject to actual valid source/calendar, selection, operational
binding, account ownership and separate owner authorization. No October19
replacement entry is permitted by that contract. A missed earlier monthly
window is not replayed. Calendar/timezone verification uses the
[official NYSE calendar](https://www.nyse.com/trade/hours-calendars) and zoneinfo;
an entry is not promised merely because the date is valid.

## DAY readback component delivered locally

`research_lab/alpaca_day_protection_v1.py` consumes a bounded authenticated GET
capture. It has no transport, credential, order, cancel, replace, re-arm or
manager interface. `scripts/audit_alpaca_day_protection_v1.py` audits one saved
capture into a create-exclusive receipt. A saved replay is labeled explicitly;
it is never presented as a fresh broker observation.

It requires clock/calendar agreement, fresh source times, verified account and
stable ledger, complete order listing, exact owned ID, quantity, side, type,
floor and an actual GET-order readback. Fractional DAY and existing whole-share
GTC protection remain distinct. A missing stop in a regular-session observation
produces `DAY_STOP_MISSING / CRITICAL`, without an invented grace period.
Pending/foreign/partial-source/conflicting evidence is UNKNOWN, never protected.
Closed hours do not count as a regular-session missing-stop incident.

Session reporting includes first confirmed-protection delay, missing/unknown
sample counts and observation gaps. Exact continuous unprotected minutes remain
`null / UNKNOWN_BETWEEN_POINT_OBSERVATIONS`: point samples cannot prove all
events between them. No synthetic zero or fabricated historical outage duration.

**152 targeted tests PASS**, including 28 new observer cases, existing repaired
Dynamic/owned-stop manager, monthly native binding and health auditor tests.
The global suite was not rerun or declared green.
[Verification](evidence/alpaca_day_protection_20261017/verification.json).

**Not yet delivered:** recurring source capture/scheduling and alert dispatch
wiring for this component. No new observer service, timer or Telegram sender
has been activated. This local component is not falsely called completed
operational DAY monitoring. Finish that wiring in isolation, verify its source,
ownership and alert/readback path orders-OFF, then provide the exact activation
packet. Existing manager and NET remain independent throughout.

## KITY and Elder boundaries

KITY's actual best complete attempt remains 9/10 filled/protected followed by
safe-flat, not 10/10 PASS. The later single IOC zero-fill attempt and watcher
READY are preserved historical facts. Policy9051 expired October16 21UTC unused;
no old launcher/GO/capture is reused. Batch/private-WS is next engineering,
then fresh bounded policy and separate personal owner money action; no cap,
price-band or rounding expansion. Execution micro does not wait for October22,
but remains separate from frozen research/C1–C3 strategy-canary eligibility.

Elder standalone stays KILL. Only frozen `ELDER_CRASH_HEDGE_V1` is prepared
orders-OFF, reusing shared ownership/transport/recovery. The October16 contract
requires at least30 hedge-events, intention/execution parity, restart/latency
checks and its existing research gate before a bounded-money dossier. No Elder
orders, outcome rerun or strategy retuning is authorized by this note.
