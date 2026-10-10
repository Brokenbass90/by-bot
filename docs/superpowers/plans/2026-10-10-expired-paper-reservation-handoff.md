# Continue the approved pre-open preparation: expired non-dispatch handoff

Purpose: remove the proven never-dispatched Oct9 attempt from active authority
without losing its original plan or repricing/resending it. No money or research
rule change. Existing policy, slots, selection, risks and caps stay exact.

- [x] Preserve fresh GET-only broker/source-store evidence. Source pin drift,
  XOM position/order, client-ID not404, any PAPER dispatch boundary, unexpired
  window or unresolved ownership => BLOCKED, never a retirement.
- [x] Append retirement evidence and future attempt history to the existing
  DynamicBook. Original intents/slots/rankings/exits bytes remain unchanged.
  New selection uses active non-retired intents; old receipt cannot become a
  child/fill. Replays are idempotent, conflicting evidence fails closed.
  Session budget counts every attempt, including retired history.
- [x] Bind the opening controller to active history, preserving old-book
  compatibility and rejecting duplicate/conflicting active lineages. No empty
  fresh-book shortcut. Targeted RED/GREEN, no full-suite side effects.
- [x] One financial review of the actual evidence/procedure. No real state
  application before reviewed source-bound proof and current CAS/shared lock.
  Freeze actual disposition and next packet gate; commit/push/remote verify.

Review-only application procedure is an exact append-only transaction on the
existing book under the original shared PAPER lock after a fresh broker GET.
No broker POST/DELETE, writer restart, LIVE HALTclear, or entry arm. A source
declaration is not authentication. Ordinary local fixtures prove mechanics only.
Next weekly ranking/source packet and exact PAPER attempt remain separate gates.

Independent ETS work is pre-due metadata only; preserve original19UTC job.
Crypto remains exactly two unchanged baseline families; Claude owns prereg/data
independence/context tests. No Gold/new families, outcomes or judges this cycle.
