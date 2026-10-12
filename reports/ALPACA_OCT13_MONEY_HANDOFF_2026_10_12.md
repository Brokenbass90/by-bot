# Alpaca P0 — October13 lifecycle and Dynamic LIVE handoff

**Current: `PAPER_PROTECTED / ORIGINAL_NEXT_DAY_GUARD_RUNNING`.**
**Dynamic LIVE: `LOCAL_INTAKE_PREPARED_ORDERS_OFF / LIVE_PORT_REQUIRED`; LIVE stays HALTED.**
Brain V1.1 is terminal STOP_V1 and is not a money prerequisite. No extra
statistical PAPER cycle, strategy research, Factory gate or risk increase.

## Fresh October12 verification

Authenticated GET/SQLite-RO capture at **15:41:23.318 UTC / 18:41:23 Cyprus**:

- NET PAPER: one full BUY **0.325167779 @ $363.20**, original full DAY sell-stop
  **$329.66**, `new`, remaining protection quantity **0.325167779**.
- Original guard PID **1979385**, active/running, NRestarts **0**. Opening job
  completed exit0; no repeat entry, resend, reprice or restart.
- All **81** installed application files and packet/manifest pins unchanged.
  Same full native ownership/HWM/floor; offline captured-state restore PASS.
- LIVE: positions0/orders0/HALT, cash **$496.12**, published accrued/pending
  regulatory fee fields0. This is a current account snapshot, not terminal cost
  proof for the still-open PAPER position.
- Production PIDs **1648585 / 1623208 / 1584802**, all NRestarts0, unchanged.
  Five legacy PAPER holdings and NET exclusion remain outside candidate writes.
- Broker writes0, remote writes0. Private capture SHA:
  `bd29ce06b2bcb88e7308786e739ad82e933f700bfea71f693e3348b98d4d65a0`.
  Public validation: `evidence/alpaca_net_paper_20261012/pre_tuesday_receipt.json`.

## Original Tuesday execution — already owned by the server

| Cyprus / UTC, October13 | Existing action / read-only observation |
|---|---|
| 16:30 / 13:30 | Original guard performs actual DAY re-arm if held overnight |
| 16:32 / 13:32 | One read-only source check of actual re-arm/protection |
| Not before16:35 /13:35 | Original scoped owned PAPER unwind |
| Hard end17:00 /14:00 | Original guard fixed deadline, never extended |
| 17:05 /14:05 | One final read-only capture of exit/cost/retirement sources |

Server execution does not require the user computer or an active Codex turn.
The **Codex observation** heartbeat requires its normal app/host availability;
it never performs the trading actions. `alpaca-net-13` is ACTIVE for the two
requested Tuesday checks only; pause after the second or a terminal result.
Keep silent on unchanged state, notify sourced re-arm PASS/material blocker/
failure/completion/required owner action. No new session or schedule extension.

First observation uses the already-published `capture_post_attempt.py` with a
new private output. After re-arm, **do not** run the initial two-order/PROTECTED
`verify_post_attempt.py`: its assertions belong to the original entry snapshot.

Final observation command, once due (GET-only, not a PAPER attempt):

```bash
.venv/bin/python reports/evidence/alpaca_tuesday_preparation_20261012/capture_finality_read_only.py .private/alpaca_net_paper_20261012/terminal_20261013.json
```

It reuses the published bounded reader and adds both accounts' activity sources.
Output is exclusive/private; originals stay untouched. The local/remote
not-before timestamp is the **existing** October13 13:35UTC unwind boundary.
Source pin/query compilation passed, script has not contacted a broker yet.
Validation: `evidence/alpaca_tuesday_preparation_20261012/preparation_validation.json`.
Each100-row activity page is incomplete; missing fee events/pending fields or
publication coverage cannot become zero cost or finality. Preserve exact
STOP/MARKET fill provenance, partial quantities and native journal retirement.
No account-wide flattening, legacy adoption, uncertain dispatch resend or fake
PAPER PASS. A concrete failure gets one exact reason and a next executable step.

## Dynamic LIVE boundary — close this engineering task before money GO

Measured code facts, not another research gate:

1. `research_lab/alpaca_open_dispatch_v2.py` and
   `research_lab/alpaca_dynamic_paper.py` intentionally expose **PAPER only**.
   Their source-frozen current server copy is unchanged.
2. `scripts/alpaca_adaptive_paper.py:977` validates the **monthly** LIVE entry
   schedule. A weekly Dynamic candidate cannot be sent through that path by
   relabelling its source/session. Passing PAPER or clearing HALT is insufficient.
3. Native ownership, protection/HWM/monotonic-floor, fill recovery and kill
   helpers already exist in `scripts/equities_alpaca_paper_bridge.py`; reuse
   them in an explicit isolated Dynamic LIVE adapter instead of weakening the
   old monthly/PAPER guards or implementing another portfolio framework.

The local intake boundary is now implemented in
`research_lab/alpaca_dynamic_live_intake_v1.py`, tested without broker operations:

- Compile an inert quantity/limit BUY with distinct deterministic LIVE IDs; later
  reads cannot change those IDs. No credentials, HTTP transport, reservation,
  sender or owner-GO authority exists in this module.
- Reject PAPER-book/validation-exit adoption, wrong account/endpoint/plan/source,
  pending PAPER lifecycle, UNKNOWN/future/contradictory quote CTS, source/ownership
  conflicts, capital/position/session excess and insufficient cash after reserve.
- Map exact terminal/partial BUY + full native stop readbacks into the existing
  manager record format, explicitly tagged Dynamic selection. Wrong/rejected/
  already-executed/underfilled protection cannot become a handoff. Original native
  validators are reused; first source/HWM/floor persist across exact replay.
- **196 targeted tests PASS**, including48 new boundary tests. This proves local
  input mechanics; scope/hash declarations are not authenticated source custody.
  The native record is returned, never installed. No actual LIVE source/session,
  dispatch/recovery runtime or manager integration is claimed complete.

Full repository verification: **4504 PASS /60 failed /1 warning**,212.30s.
No failure in the new intake file. Exact names/log hash are preserved in
`evidence/alpaca_tuesday_preparation_20261012/live_intake_validation.json`.
Current HEAD baseline was not rerun; the older Oct4 57-failure receipt does not
prove these60 are all pre-existing. No global-green/no-regression claim.
Independent reviewer remains unavailable; root boundary review only.

The remaining runtime integration is narrowly scoped:

- New Dynamic LIVE entry scope with exact endpoint/account/policy/source pins,
  fresh validated opening quote/cash/assets/fees and one independently reserved
  LIVE slot. Preserve the PAPER book; never promote its buy, quantity, intent or
  validation unwind into a LIVE holding/exit/vacancy.
- Reuse the frozen weekly selector/ranking and inherited actual-OLD terminal
  lineage. New LIVE evidence must bind its own time and fresh sizing, rather
  than replay the October12 PAPER plan or claim Sep30 selection.
- Same caps: **$487.42 capital / gross0.70 / max4 / one entry per session**;
  inherited selected slot notional ceiling **$124.699999985736** and stop-risk
  ceiling **$10.906127324106**. CAT/source-bound liabilities reduce funding.
  No risk enlargement, forced rotation, market-price substitution or new scan.
- Preserve quantity-limited limit BUY, actual-fill-relative frozen distance,
  full native protection/readback, original shared account lock and exact
  once-only IDs. Unknown dispatch cannot resend; partial/422/restart must retain
  native protection/owned emergency sources. One entry owner and one manager;
  old monthly entry authority must remain OFF.
- Verification before activation: no GO/no lifecycle proof ⇒ no broker write;
  LIVE/PAPER account mismatch, altered plan/source/caps, duplicate/restart,
  partial fill, uncertain BUY/STOP, 422 protection failure and existing-manager
  ownership cases. Root financial review must disclose the existing independent
  reviewer limitation; never claim unperformed signoff.

The local compiler/handoff candidate is implemented, but the full runtime adapter
is **not integrated/installed/approved for sending yet**. Do not
mark READY_FOR_LIVE_GO until this implementation and the actual lifecycle are
both complete. This is the next concrete engineering task, with no new research
or statistical waiting. Source/endpoint guards must not be bypassed under an
owner's broad wish to start trading.

## Exact promotion and first eligible entry

After a clean existing lifecycle and tested native Dynamic LIVE adapter, produce
one precise ticker/qty/notional/stop-distance/fees/liabilities/ownership/kill/
rollback dossier. Request the **separate** owner GO only on that concrete packet.
No HALTclear/order/CRWD-META rebuy now; a fresh LIVE plan is required at its own
permitted opening. The sealed calendar includes October14 **13:30UTC /16:30
Cyprus**. Since the current validation unwind starts after Tuesday's five-minute
entry window, October14 is the earliest next opening after that lifecycle/GO;
it is conditional on completed engineering and the original fresh gates.
No guarantee of a particular execution date or positive PnL is inferred.

KITY keeps its own frozen October15/22 evidence path. Bounce/Breakout/Elder and
Factory remain Claude's lane; no Brain rescue, new strategy family or liquidation
source deployment in this Alpaca preparation cycle.
