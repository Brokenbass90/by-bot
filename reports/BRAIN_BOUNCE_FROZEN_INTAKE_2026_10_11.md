# Brain V2 / BOUNCE1 — October 11 frozen intake and terminal engineering delta

**No financial or LIVE authority. Alpaca NET arming remains untouched.**
Delivery receipt: [terminal_readiness.json](evidence/brain_bounce_intake_20261011/terminal_readiness.json).
Local recovery base `2adc742`. Claude immutable research commit
`10a76a02bc8ed0a8d5b120c92c314167db8160d3`; origin advanced during this cycle to
`2b7a960ec29cca509f34bdc677795fe467ac5384`. All five exact frozen files match that
published origin. Initial origin `b9a95b4` lacked this new spec; that observation
is superseded by the actual published equality check. No branch merge/checkout,
Claude edit, research outcome read or judge was performed.

## P0 — Brain V2: primitives PASS, integrated system BLOCKED_DATA

Implemented [brain_v2_frozen_primitives.py](../research_lab/brain_v2_frozen_primitives.py):
immutable opportunity and content ID; exact 300/150 shrinkage, z and clipped
0.5–1.5 sizing; negative scores remain ranked rather than vetoed; UNKNOWN
context falls back to sleeve mean; missing statistics/cells are not inferred
as zero. Statistics require frozen provenance and outcome availability strictly
before October 1, 2025. No statistics are fitted or historical streams read. Exact venue-native Unicode
symbols are preserved; no ASCII-only universe filter or transliteration is added.

The adapter uses the A1-pinned existing regime math on last 200 closed BTC H4,
requires the expected last bar and last 60 contiguous bars, and emits UNKNOWN
for absent/future/incomplete/unavailable input. It never writes regime.json.
VOL classification implements only exact `<33 / 33..67 / >67` boundaries on an
externally frozen percentile; no ATR/percentile estimator was invented.

Exact proposed-portfolio assessment checks 6% equity risk, 12 positions,
1 symbol, 40% sleeve share of **current total open risk**, and 60% absolute
net direction of that same total. Decimal arithmetic avoids an invented epsilon.
UNKNOWN capital/positions/protection blocks. Three separate inert sizing receipt
sections are not three operating portfolio ledgers or a prospective comparison.
No autonomous subset allocation, capital mutation, order path or broker credential
exists. Opportunity ordering uses earlier t_available then ID, unlike the older
router's later-timestamp tie-break. It does not inherit that router's score veto.

**Exact integrated blockers requiring a frozen Claude addendum:**

1. Whole-hour subset/bootstrap selection is unspecified. Every first entry of
   an empty FOUNDATION/BRAIN portfolio has 100% sleeve and 100% direction and
   violates both literal caps. A simultaneous three-sleeve balanced proposal can
   pass. Rank alone does not define which feasible batch to choose, how to use
   empty slots, whether to skip a high-ranked infeasible subset or allow a
   bootstrap exception. Codex did not reinterpret these caps as shares of 6% E.
2. VOL requires a source-locked ATR smoothing, empirical percentile/tie method,
   exact 90-day endpoint/current-observation convention and warmup/coverage.
   Source primitives have multiple ATR variants; choosing one changes features.
3. Actual frozen train μ/σ table and its source/availability/cell-completeness
   contract are absent. The function consumes externally supplied statistics;
   analytical fixtures are explicitly synthetic, not an accepted train table.

[Cap counterexamples](evidence/brain_bounce_intake_20261011/synthetic_cap_counterexamples.json)
and [inert primitive receipt](evidence/brain_bounce_intake_20261011/synthetic_primitive_receipt.json)
reproduce the distinction. Do not announce `BRAIN_V2_ENGINEERING_READY` or start
paired prospective clocks from this partial candidate.

## P1 — BOUNCE1: BLOCKED_DATA, closed count UNKNOWN

Read-only VPS metadata at `2026-10-11T20:02:09Z`, followed by bounded actual
process-path verification. PID1648585 runs `smart_pump_reversal_bot.py` from
`/root/by-bot`. Expected state and ledger at
`/root/by-bot/runtime/bounce1_shadow_state.json` and `bounce1_shadow_ledger.jsonl`
are absent. No absence is claimed for every possible unobserved archive/custom
path. No closed-decision count can be certified; this is **UNKNOWN, not zero**.

Current heartbeat/diagnostics report BOUNCE enabled/risk0 and universe
`ADA, AVAX, DOT, HYPE, LINK, SAND, SUI, ZEC`, not preregistered BTC/ETH and not
BOUNCE1_8's proposed eight majors. The approved on-disk env still says BTC/ETH;
file configuration therefore is not in-memory authority. The original August8
receipt lacks a deployment commit/source pin, so it cannot establish continuous
historical source identity after this mismatch.

Current on-disk strategy SHA `65fee98f…` differs from frozen `1f073053…`;
wrapper `9f89685b…` differs from local `5063ad15…`; main also differs. These are
current file hashes, not a claim that already-imported process memory has those
exact bytes. Writer `46e1a089…` and approved-env `52de3558…` match local pins.
Full source hashes and safe selected values are in
[bounce1_vps_metadata.json](evidence/brain_bounce_intake_20261011/bounce1_vps_metadata.json)
and [actual process paths](evidence/brain_bounce_intake_20261011/bounce1_process_paths.json).

Current on-disk main contains all eight expected shadow producer anchors,
recorded in [producer anchors](evidence/brain_bounce_intake_20261011/bounce1_producer_anchors.json).
Their presence does not prove callbacks execute, the ledger path is unchanged,
or the historical cohort/config identity. No absence of producer code is claimed.

**No KEEP/KILL look.** It remains prohibited before 30 uniquely closed,
source-verified decisions and the F1 funding/availability contract. `signal_id`,
not a nonexistent `decision_id`, is this writer's closed-unit identity.
Next finite action: Claude/source owner supplies exact legacy ledger location
and deployment/config/source continuity proof or withdraws the August8 cohort
claim. No silent adoption of the runtime's different universe or fake n=0.

The first metadata query used two nonexistent service aliases; those inactive
responses are not evidence of a production outage. The actual-unit path check
confirms bybot PID1648585 and ATT1 lifecycle PID1584802/NRestarts0 unchanged.
The web PID was not rechecked. No production process was restarted or changed.

## P2 — BOUNCE1_8: BLOCKED_IMPLEMENTATION, not running

[Separate source candidate](evidence/brain_bounce_intake_20261011/bounce1_8_source_candidate.json)
binds §6 prereg, original `62f196e5…` config, exact `1f073053…` strategy and
BTC/ETH/SOL/ADA/LINK/LTC/DOT/SUI. Money risk0, separate candidate ID/ledger,
6+2bps and F1 funding are preserved. No epoch, service or first decision exists.

**Exact blocker: the reusable legacy ticker writer does not satisfy the
preregistered causal closed-bar next-open/F1 lifecycle.** Synthetic protocol
counterexamples demonstrate late-tick fills, missed intrabar stop-before-target,
missing funding/source pins, and corrupt-state reset/duplicate identity. They
are not prospective outcomes. Existing producer/writer is deliberately unchanged.

Frozen baseline source facts: selector is called once per M5 only while no open
or pending symbol; KlineStore exposes completed H1/H4; signal availability is
execution-bar close; next-open pending fill is processed before the next bar's
OHLC stop/targets; stop wins if both hit; partial targets in fixed order; time
stop afterward. Strategy cooldown decrements by calls and its cache/cooldown
are not persisted. The live fetch wrapper includes the latest provider candle;
blindly copying it does not establish closed-data parity.

Next finite implementation contract: freeze the public-only closed-data and
receive/availability-to-next-open timing; preserve original partial/fee and
stop-first semantics and specify F1 application at the source exit timestamps;
then test restart/corruption/source-gap behavior before independent deployment.
Do not deploy eight allowlist names on the old monolith and call it this epoch.

## Verification and boundaries

73 targeted local tests PASS (51 Brain, 4 protocol counterexamples, 2 original
shadow, 16 existing OS2 regressions). Initial missing-module RED, a real
post-develop-statistics failure and malformed UNKNOWN/position failures were
retained in session output and corrected with targeted RED→GREEN checks.
One verification command named a nonexistent regime test file and ran no tests;
it was corrected to the actual existing targeted set. Full suite not rerun and
historically NOT_GREEN. No VPS implementation/testing claim.

Bounded critical reviewer runtime verified gpt-6-astra/high but stopped at its
usage limit, so **no independent review delivered**; no retry or expensive
replacement. Root source/math/self verification is weaker and is not a READY
or authority claim. Mechanical source inventory runtime gpt-5.6-luna/medium,
read-only/no edits. No percentage cost-saving claim.

No Alpaca unit/session/config/state access, no broker calls/order path, no new
service/cron/automation, no ATT1 changes, no KITY/B3 work, no Claude message or
source edits. Foreign allowlist SHA remains
`add587f1bd7059c2c706f1f7c604e36c2fb7b36b258b127e01fcd2101d3f19a1`.
Alpaca's prior actual arming receipt remains the authority for Monday16:30–16:35
Cyprus PAPER NET; first overnight DAY re-arm is TuesdayOct13. LIVE remains
outside this authorization, with separate exact dossier and owner GO required.
