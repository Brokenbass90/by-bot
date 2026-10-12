# Brain V2 A1/A2 — local engineering delivery, October12

`BRAIN_V2_ENGINEERING_READY / ORDERS_OFF_LOCAL` for the source-pinned local
hour allocator, context/scorer, three independent arm ledgers and paired journal.
This is not developing-filter PASS, prospective start, standalone edge or money
readiness. No worker, broker adapter, credentials or order path was installed.

Verified origin research **47069002b5d189572b4a839e38c514e5d485f435**; no merge,
Claude checkout edit or research push. V1 spec `f96b73ec…fd6c0` and params
`305a00c7…bc157` are unchanged. A1 changes the denominator relative to the original
V1 prose; earlier literal-cap code/receipts remain preserved. A2 confirms that the
40% cap covers the aggregate sleeve, not one position, and fixes context timing.

Active table **35fa0e0809b0df2f63ef29d5c1483158573d35d6fb25212e79c1cfe500557020**
is `MU_SIGMA_V1_A2`. A1 `55c32948…2092` is retained in its original snapshot but
is rejected by the new loader. All six sleeve n/mean/mu/sigma values agree within floating precision;
context populations changed. No Codex generator execution or raw B3 outcome read.

Implementation: `research_lab/brain_v2_a1.py`, preserving the V1 module. The new
engine uses the existing OS2 journal via default-preserving schema/assessment
hooks; OS2 regression tests verify its unchanged default behavior. Separate
RAW_SAFE/FOUNDATION/BRAIN_DET capital, positions and final-cost closed ledgers
reside in a single atomic paired transaction; no arm shares capital or positions.

- H1 sleeves: t_available = signal bar open+1h; ETS2/SF3:+15m. Context and
  batch use floor(t_available), VOL uses the closed H1 opened at h−1h.
- VOL: first14TR mean then Wilder recursion, 2160 NATR values including current,
  midrank ties; gaps/missing/warmup/nonfinite/future availability stay UNKNOWN.
- Pinned table loader verifies exact bytes, populations and shrinkage. Regime
  names map explicitly BULL↔BULL_TREND/BEAR↔BEAR_TREND. Omitted zero cells are
  accepted only because exact pinned known-cell+UNKNOWN counts exhaust n.
- Risk budget .06E, base .005E, 12 slots/one symbol, sleeve .40B and net-direction
  .60B for FOUNDATION/BRAIN only. Greedy violation priority is exactly frozen.
  E is each arm's realized capital after the current hour's known actual exits;
  no MTM rebasing or positive-score veto. Existing positions are not resized.
- Every final outcome records gross, fees6bps/side, slippage2bps/side and signed
  actual funding separately. Table R is ranking-only; never reused as cash PnL.
  Funding and exit-notional ratio must be explicit/source-pinned, finality known.
- Prefix hashes, one writer, idempotent requests and semantic replay on restart;
  corruption/conflicting ID/uncertain append fail closed. No truncation/repair.

**182 local targeted tests PASS**, including 51 preserved V1 primitives and all
existing OS2 bridge/journal/CLI/review regressions. New tests include analytical
budget/sleeve/direction limits, rejection continuation, independent arm equity,
full costs, exact restart, uncertain fsync and pure-function parity with the A2
generator on synthetic bars only. No VPS test or full-suite-green claim; the
historical broad suite remains NOT_GREEN and was not rerun.

One final root review reproduced and fixed three defects RED→GREEN: process-wide
Decimal settings affected receipts; NaN BTC data crashed adapter hashing; a
malformed terminal raised KeyError. Numerical representation now has isolated
50-digit Decimal context and canonical closed-cash summation, without venue
rounding or changed risk numbers. Independent6-astra review previously hit quota;
it was not retried/replaced and this is **not independent financial signoff**.

Remaining gates, with concrete next actions:

| Gate | Current state | Next action |
|---|---|---|
| Four developing train tables/filter | NOT_RUN | Freeze A2 tables at four original cutoffs/hashes before any frozen comparison; preserve source and funding/MTM input completeness. Claude research lane, no B3 rerun. |
| Actual-source Brain shadow | NOT_STARTED | Bind complete causal opportunity/terminal/mark manifests, canonical H1 history origin/Wilder seed and table publication time; prove source adapters/retention bound before a separate prospective epoch. |
| Same-hour new entry and exit / delayed finality | BLOCKED_DATA on such input | Engine never credits a not-yet-admitted trade or rewrites a prior hour. Actual-stream integration must resolve this causally before claiming lifecycle readiness. |
| Mixed H1/15m whole-hour batch entry time/price | BLOCKED_RESEARCH_TIMING_CONTRACT; exact question sent to owner for Claude | A1 requires the complete hour while 15m opportunities arrive during it. Freeze when selection is known and the virtual fill price/time for all arms before any comparison; never reuse an earlier price after seeing later opportunities. |
| Historical developing-period use | Not supported by this active table | Fixed prospective table cannot replace per-fold train tables or look backward into their test outcomes. |
| BOUNCE1 old shadow integrity | Previous dated BLOCKED_DATA | Recover exact Aug8 ledger/config/source continuity and unique closed count before any30/60 judge; Oct12 no new VPS read/count claim. |
| BOUNCE1_8 | Previous BLOCKED_IMPLEMENTATION / NOT_DEPLOYED | Separate closed-bar-next-open/F1 lifecycle first, not a legacy tick-writer deployment. |

No attempt here consumes developing/holdout outcomes, runs a judge or promotes a
policy. The review/candidate only closes the former missing allocator/VOL/table
implementation blockers. See the runbook and machine delivery receipt for bounds.

Alpaca NET remains outside this diff and outside all new authority: original
MondayOct12 **13:30–13:35UTC /16:30–16:35Cyprus** PAPER session, no restart/rescan/
extension or LIVE entry. Prior Sunday arming receipt is dated, not a fresh Oct12
broker snapshot. Its actual lifecycle/re-arm/finality gates remain independent.
ATT1/KITY/B3 and foreign allowlist untouched. No service/broker or Claude branch writes.
