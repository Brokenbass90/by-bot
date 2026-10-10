# October10 source preparation — no outcome run

**Bounce source mechanics delivered; terminal `BLOCKED_RESEARCH_SOURCE_CONTRACT`.**
The existing BTC/ETH majors baseline now has a pinned universe/config, closed
H1/H4 artifacts, preparation/as-of receipts and the original historical fee/
slippage assumptions. It is not `BOUNCE_RANGE_PREREG_INPUT_READY`: funding,
historical source lineage/PIT availability and independent validation are still
unproven. This is a finite research-input handoff, not a strategy verdict.

## Bounce/range

[Source manifest](evidence/source_preparation_20261010/bounce_manifest.json).
Actual data live in `research_lab/data/bounce_range_sources_20261010_v2` (ignored
data directory); canonical JSONL artifacts and exact SHA256s are in the manifest.
No sealed input was overwritten. Each of BTC/ETH has 31,635 H1 rows and 7,908
complete UTC H4 bars, from the existing Jan2023–Aug2026 source. Three initial
H1 rows per symbol are explicitly excluded from H4 because the source starts at
01:00 UTC; no shifted four-hour bucket or incomplete last H4 is invented.

The legacy H1 builder uses **opening timestamps**. The new pure derivative
requires `open + interval <= as_of`, contiguous full-hour UTC grid, four complete
children per H4 and declared12 M5 sub-bars per H1. It rejects duplicates, gaps,
open/future candles, invalid count, malformed price geometry and nonfinite data.
It reuses existing canonical OHLCV validation. Count12 does not prove a raw M5
grid; historical provider/publication lineage remains unproven. The stored
float32 prices are widened, never claimed to regain original exchange precision.

The two-symbol universe comes from the existing majors prereg and approved
risk-zero configuration, not a new selection from outcomes. The eight-symbol
prereg remains a separate hypothesis. SL1.6/TP1 fraction.15/trail0 are the frozen
majors overrides; other literal defaults are preserved in the packet. No env
overlay was loaded, no strategy constructed or called. The future native runner
must isolate all BOUNCE1_/ASB1_ overrides: its constructor reads environment.
The baseline already contains its native H4 context rule; no extra trend filter
was added here.

Cost sources: `configs/research/bounce1_majors_three_regime_prereg_20260802.json`
declares next-open execution, fee6bps/side and slippage2bps/side. These are frozen
historical assumptions, not a measured spread or current account-fee attestation.
Neither that prereg nor the eight-symbol prereg declares funding treatment.
Missing funding stays unknown, never zero; no new funding policy was invented.

The three declared120-day windows ending2024-01-29,2024-12-30,2026-04-30 are
potentially consumed, not untouched. A full discovery/consumption ledger is
absent; Jan2023–Aug2026 cannot simply be relabelled holdout because some bars
fall outside those windows. No independent historical interval is certified.
Forward collection is an alternative only after the complete source/config/
cost/context/judge freeze, with no retroactive start.

Claude's exact remaining source actions before any outcome run:

1. Declare funding debit/credit/timestamp/missing-data treatment and bind complete
   venue histories; changing old cost semantics requires an explicit version.
2. Supply actual raw M5 provider/assembly/availability lineage for the cached H1,
   or use a separately pinned source with its own honest provenance. The builder
   historically deduped/chose overlapping files and did not retain a manifest.
3. Declare consumed/discovery spans and an independently justified validation
   interval with hashes, or freeze a genuinely new forward period. Then prereg
   the baseline versus causal context comparison and KEEP/KILL criteria.

## Breakout/retest: exact acquisition plan

[Machine plan](evidence/source_preparation_20261010/breakout_acquisition.json).
The current parity adapter deliberately keeps the older Phase0 blob. The existing
Phase1 prereg pins the causal M5→H1 expansion→later M15 hold/retest/pivot/BOS→
exact next-M5-open contract, levels, execution and durable outbox. All17 component
pins and both input-manifest hashes match locally. Phase0 parity is not Phase1
parity; no adapter/source was silently swapped.

The exact13 Dev13 raw M5 files are **absent** at their pinned paths in recovery,
Claude's clean-v28 and the Alpaca compatibility checkout. Manifest existence
does not mean data exist. Recover the retained original snapshot archive and
require exact raw hashes; if irretrievable, the original Dev13 source is blocked.
A fresh download must be a separately frozen source identity, never an old-manifest
repin. Derive M15/H1/H4 from one validated closed M5 prefix through the existing
aggregator, then canonical pre-event H1/H4 horizontal-level snapshots. Funding
coverage and consumption/independence remain separate inputs. The plan lists
exact sources/expected hashes, sequence and original costs. No judge/level
outcome scan or new OOS result was accessed.

## Monday Alpaca static intake

[Static intake](evidence/source_preparation_20261010/alpaca_monday_static.json):
**`STATIC_SOURCES_PINNED_NOT_DISPATCHABLE` / `BLOCKED_DATA_NEXT_SESSION_PACKET`.**
Policy, exact account IDs/endpoints, shared original lock/book/runtime, inherited
slot caps, global fractional/protection eligibility and fee-liability contract
are pinned. Unknown candidate/earnings/concentration/ownership/cash/review fields
are null, never inherited True from the old XOM attempt or its retirement permit.
The existing executable runner was not changed, installed, armed or invoked.

The Oct10 09:35UTC broker snapshot remains the last dated source, not Monday
truth. No VPS/SSH/broker operation occurred in this source-preparation cycle.
LIVE HALT/caps and five legacy PAPER positions remain outside new entry authority.
No Oct9 XOM exists to re-arm Monday. A first Monday entry held overnight has its
next actual DAY re-arm TuesdayOct13; that future gate is not today's PAPER PASS.

Finish the actual weekly Oct9 closed-session ranking and resulting symbol's
static earnings/reentry/concentration/protocol/owner/exclusion/template before
the next opening. The old XOM protocol contains a symbol-specific asset binding:
global fractional support alone is not a new symbol's prepared contract. Pin
the accepted symbol explicitly and review it; no automatic True flag copy.
CAT plus actual unresolved liability must reduce spendable funding before
reservation. Fresh fees/account/cash/quote/asset/ownership still fail closed.

Static completion deadline Monday13:15UTC/16:15Cyprus; READY13:29UTC/16:29Cyprus;
opening13:30–13:35UTC. The opening path contains only mandatory fresh checks,
reservation and one existing PAPER adapter call. No helper coding, history
reconstruction or review in that window; uncertain dispatch is GET recovery,
not resend/reprice. Separate owner LIVE GO remains mandatory.

## Verification and preserved boundaries

69 targeted checks PASS for source derivation/preparation, existing baseline
adapter parity and canonical aggregation. New derivation tests were RED with
the module absent before implementation. This is neither a full-suite PASS nor
a broker lifecycle/edge result. Targeted command:

```bash
.venv/bin/python -m pytest -q tests/test_bounce_range_source_packet.py tests/test_crypto_core_v2_baselines.py tests/test_closed_bar_aggregation_v1.py
```

One bounded independent financial/causal review found a verification/read race.
The preparer now parses exactly the bytes it verified (in-memory NPZ/JSON),
records consumed hashes and rejects any source change before writing output.
Two race regressions were RED before the fix and GREEN after. The original
derivative directory/manifest is retained; v2 data bytes/hashes are identical
with a new actual preparation/source-code receipt. Same-review closure and
runtime model/effort are recorded in the verification receipt. Existing full-suite NOT_GREEN limitation remains; no
broad suite or foreign allowlist edit. No orders, strategy research run, B3
rerun, ATT1/KITY rescue, Gold work, Factory/AI/Claude edit or message. ETS2M's
original Oct10 19UTC/22Cyprus job/cohort pins remain untouched; this earlier
source cycle supplies no new terminal ETS verdict.
