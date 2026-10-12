# Brain V2 A3/A4 delivery — October12 morning

**BRAIN_V2_ENGINEERING_READY / A3_A4_ORDERS_OFF_LOCAL.** Frozen timing and
UNKNOWN-cash questions are closed; actual research/shadow/money are not started
or approved. Continue the existing A1/A2 candidate; no primitive restart.

Owner-supplied A3@1e4773bef1b5e21d764aaac348efe282737f64b9 and
A4@23411ae0e3a651af145462bf1734cf23ca25432d were inspected as single-addendum
commits and published by the owner's explicit push instruction. Actual origin
and recovery FETCH_HEAD verified23411ae. No Claude working-file edits, branch
checkout/merge, research generator, new trade-outcome read or judge execution.
Seven immutable control sources and exact hashes are preserved in
`evidence/brain_v2_a3_20261012/source_manifest.json`. Spec f96b73ec…,
params305a00c7… and A2 table35fa0e08…7020 are unchanged.

`research_lab/brain_v2_a3.py` is a distinct state/receipt version:

- Exact15m ticks; a package contains only t_available==tick. Future opportunities
  cannot enter an earlier decision; off_grid is an explicit rejection. H1/15m
  source mapping is A2; context remains at floor(tick)/hour.
- Releases precede allocation. Entry is the original B3 next-open at the tick.
  Entry metadata contains only source-bound stream lev; neither R nor actual
  hours/release outcome can affect ranking or allocation. This module does not
  reconstruct prices or resimulate the original streams.
- Source R already contains6bps/side: net=R*risk−.0004*notional−signed funding,
  with notional=risk*stream_lev. Rounded original lev is retained; it is not
  recomputed from stop distance. Terminal hours/release must match the causal
  tick. A missing/late terminal cannot backdate equity.
- Funding requires the exact Bybit symbol/archive and separately pinned complete
  settlement calendar for entry<t<=release. No universal8h interval is assumed;
  an empty rate array alone cannot prove zero funding. Missing or late rates
  produce FUNDING_UNKNOWN. Missing calendar/source identity blocks intake.
- A4 frees risk on schedule for FUNDING_UNKNOWN, records **null whole PnL**,
  leaves E unchanged, and excludes it from cash metrics. Counts, slot-hours and
  risk are reported separately for each arm. Late funding cannot re-credit E.
  Strict greater-than5% in any arm is a developing data-coverage BLOCKED result;
  this diagnostic does not become an unapproved entry veto.
- Three arm ledgers remain independent inside one atomic paired transaction.
  Existing caps, shrinkage, ordering and0.5x–1.5x sizing are reused unchanged.
  Existing single-writer/fsync/hash/replay guards are reused; no new framework,
  market client, credentials, order adapter or production worker.

Verification: **231 local targeted PASS**, including49 A3/A4 checks and the
previous182 V1/A1/A2/OS2/bounce protocol checks. Five root review tests initially
failed as expected: incomplete terminal population and unexpected top-level
fields. The source/completeness guards closed all five RED→GREEN; unknown fields
are rejected before journal append. The initial synthetic proof correctly
refused a macOS tempdir symlink; resolving its owned real path preserved the
guard. `py_compile`, source7/7 hash verification and diff whitespace checks PASS.
Seven synthetic paired receipts replay identically after restart, with unchanged
raw journal bytes; proof/archive are in the evidence directory. They are not
broker executions or prospective decisions.

One bounded root financial review covered causal release/sizing, no double
commission, signed/missing/late funding, unknown cross-arm populations and
restart/uncertain append. Earlier independent reviewer quota failure was not
retried/replaced; **no independent financial signoff is claimed**. Full repository
suite remains historically NOT_GREEN and was not rerun; no VPS tests/readback.

Remaining actual gates: four source-pinned developing-fold A2 tables/hashes;
frozen developing evaluation (NOT_RUN); complete real opportunity/entry/terminal
providers and per-symbol settlement calendars/publication times; canonical H1
seed/provenance; source-known epoch, real MTM/cost integrity and reviewed journal
retention before any prospective worker. LOCAL readiness is not researchPASS,
profitability, live routing permission or LIVE GO. Do not fit/tune policy here.

Alpaca NET original MondayOct12 server PAPER opener/guard, LIVE HALT/caps, BOUNCE1
source/count gate, separate BOUNCE1_8, KITY and spent B3 remain untouched. No VPS,
broker or service operation occurred. Foreign allowlist file hash is unchanged.

Next: actual Alpaca PAPER receipt preempts Brain work; Brain proceeds with the
already frozen research/source gates above, never a B3 rerun or money activation.
Use [A3/A4 runbook](BRAIN_V2_A3_A4_RUNBOOK.md).
