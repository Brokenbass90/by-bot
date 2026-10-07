# Alpaca first Dynamic window and opening protection incident — October 7

**Terminal verdict: BLOCKED_EXECUTION; current LIVE manager HALTED, broker flat.**
The first Dynamic selection completed orders-OFF. The opening protection failure
is reproduced and a bounded local correction is reviewed/tested. It is **not
deployed** and does not reactivate LIVE or complete broker PAPER acceptance.
Read the companion JSON for exact timestamps, hashes and verification evidence.

## What actually happened

The source-only job completed at **13:30:17 UTC /16:30:17 Cyprus**. Its immutable
13:30 broker snapshot still contained CRWD and META with no active DAY stops.
At **13:30:17.649568 UTC**, the existing LIVE bridge logged a broker HTTP422:
CRWD stop **275.45** was above broker market price **275.20**. This is the proven
submission rejection; an independently read position quote does not establish
the bridge's exact pre-submit quote. `_rearm_intended_position` already rejects
a locally observed price at/below the floor, but that check cannot remove the race.

The monthly retained-name re-arm loop aborted on the first exception. META's
re-arm was therefore never reached. The existing emergency scoper freshly found
both owned positions without confirmed protection and submitted bounded exits:

| Symbol | Confirmed sold quantity | Filled price | Filled at UTC |
|---|---:|---:|---|
| CRWD | 0.469970151 | 275.43 | 13:30:21.138159586 |
| META | 0.141939508 | 736.062 | 13:30:21.442949380 |

Both orders and their FILL activities are confirmed. Combined realized gain from
these two exits is **$6.380157352418 before fees**, computed from broker quantities
and entry averages. The 13:39 GET showed cash/equity **$496.12** and pending
regulatory fees **$0.02**. This is not fee-final net PnL or a demonstrated edge.

The **13:51 UTC** postcheck confirms no positions/no open orders, persistent
account entry HALT, one NEW schedule, OLD schedules/processes absent and all
**58 LIVE source pins unchanged**. Cap **$487.42**, gross **0.70** remain frozen.
No order was submitted by this Codex cycle. The exits above came from the existing
authorized manager. Production PIDs/NRestarts remained unchanged through the
13:57 source-capture installation postcheck.

Subsequent manager runs report `intended_stop_exit_not_confirmed:CRWD`: the
retained lifecycle points to an expired stop, whereas the confirmed exit was an
emergency market order. Do not delete/retire that state or clear the HALT merely
because the broker is flat. Source-bound emergency-exit/finality reconciliation
is a remaining integration gate.

## Bounded correction, local only

Only the existing monthly pre-rearm loop in
`scripts/equities_alpaca_paper_bridge.py` changed. Each eligible retained name gets
one existing re-arm attempt. RuntimeError failures, including the actual HTTP422
and intended-protection errors, are collected while the next eligible name is
attempted. An aggregate error is raised **before rotation**, preserving the
existing entry halt and emergency path. Unexpected storage/serialization errors
retain immediate global abort behavior.

Quantity, ownership, stop floor, HWM, DAY/GTC rules, confirmation, risk, buys and
emergency authority are unchanged. A successfully confirmed stop remains durable;
fresh emergency verification excludes a protected name. No retry, repricing,
lower floor or new buying path was added. This does not prove META would have
remained open historically: its hypothetical stop still needed broker acceptance.

Verification:

- RED: 2 failed/5 passed; healthy META retained its expired stop ID after first-name
  rejection or local floor breach.
- Final targeted: **113 passed**, including first/second/both-name failure,
  persistent halt, no rotation, unchanged failed floors, actual emergency scoping,
  and accepted stop with initially uncertain readback followed by fresh verification.
- Full suite: **4054 passed /57 failed**. The exact 57 names equal the established
  baseline; no new/removed failures. They are listed in the companion JSON.
- One bounded financial review approved the local correction; runtime metadata
  independently confirms `gpt-6-astra/high`. No VPS test/deployment of this fix is claimed.
- Foreign `configs/allowlist_change_log.json` preserved byte-for-byte and unstaged.

## First actual Dynamic selection

The original October7 **13:30–13:35 UTC** window completed without retry or
extension. The native job exited. All 21 installed source pins matched. The
closed 59-name source, first receipt, schedule and SQLite were copied into a
private evidence archive; hashes and database counts independently verified.
SQLite contains one ranking, three inherited slots, **zero intents/zero exits**.

Independent offline reconstruction from the captured closed October6 bars and
the original contemporaneous exclusions exactly reproduces **XOM**:
signal close **164.4799957275**, signal stop **157.1713806152**. These are signal
references, not a current quote, executable quantity, new broker stop or approved
allocation. The ranking stays immutable despite subsequent CRWD/META exits.

The first source receipt expressly says cash-finality/actual fees unverified and
PAPER not executed. There was no plan with exact quantity/reference ask bound
before a fill. Do not backdate one or force a purchase outside the open window.

Remaining gates, in order:

1. Preserve and reconcile actual emergency exits/expired-stop records using exact
   account/order/fill provenance; retain unresolved fee liabilities and 21-day
   reentry behavior. Do not invent a successful stop exit or reset LIVE state.
2. At the next permitted open window, use the sealed weekly ranking with actual
   quote/asset/minimum/quantity, cash-liability/fee, eligibility and exclusive-owner
   evidence. Original first-window capture is not rerun. No new arbitrary scan.
3. Exercise the isolated PAPER adapter/manager on an exactly reserved plan:
   accepted full protection, partial/restart/duplicate behavior, DAY re-arm,
   terminal costs/finality and scoped unwind. Preserve shared legacy PAPER names.
4. Produce the exact handoff/rollback/kill and ticker/quantity/risk dossier, then
   obtain a **separate owner LIVE GO**. No permission to clear the current HALT follows
   from this report or from passing local tests.

## Money lane while Claude is unavailable

Actual origin research **cf904086a2d887a96ac2be3324a3d78433e1a94b** was verified
and fetched into recovery only. No merge, sibling edit, Claude message or judge run.

Claude's B3 A1 amendment publishes versioned fixes for all four findings. Its six
intake source/config/lock hashes match the amendment, and B3_KONFIG retains
`9b65e28c…2256f`. This is source-intake verification, not judge/input-determinism or
profitability proof. After KITY only, verify **all** frozen source/config/inputs,
prior consumption and deterministic execution before the owner's conditional
single B3 run. Any mismatch → BLOCKED; Codex does not repair/retune research.
SEALED_V2 strict independence is still not asserted; prospective policy evidence
and separate ORCHESTRATOR_POLICY_V1 GO remain.

Claude's external KITY Bybit receipt reports CROSS_VENUE_PASS: 187 weeks,
95.9% coverage, +57.6bps/week, t=2.06, halves +23.4/+91.4bps. Codex did not rerun
this judge or independently validate its historical outcomes. It does not supply
actual account fees/cash/mode, the unseen basket or execution permission.

To avoid losing the required PIT census, one **source-only public GET operation**
is armed independently of Claude under
`/opt/bybot-research/kity-cutoff-census-20261007`, PID **1804770**.
It reuses the unchanged approved public façade; two source files are pinned.
Fixed request target **Oct7 23:54:58.200 UTC**, fixed cutoff/deadline **23:55:00 UTC**.
A response outside the frozen two-second census window, missing clock sync,
source/resource failure or missed deadline yields BLOCKED_DATA. No retry/reset,
credentials, broker call, strategy calculation, order path, service/cron change
or Claude writer is involved. Public preflight response delay was 554ms.

This operation collects **exchangeInfo only**, not OI, candles or a signal. After
Oct8 00:05UTC, retain exact 23:55 OI for the complete eligible census and closed
daily inputs, reconstruct the frozen n//10 basket, then compare Claude's external
raw evidence. Complete input and immutable signal sealing must precede Oct9
00:00UTC. Missing or stale source remains BLOCKED_DATA; never substitute 23:50.

Priority after this terminal Alpaca result: **KITY Oct8–9 → conditional frozen
B3 once → OS2 actual-source/parity orders-OFF**. No new strategy research,
policy tuning, AI/Factory replacement or architecture expansion while Claude is
unavailable. ATT1 completed-probe/2–3 clean terminals+dossier+GO and ETS2M original
900/deadline blockers remain unchanged; they were not re-audited in this cycle.
