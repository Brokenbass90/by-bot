# KITY M3 isolated execution assessor — orders OFF

This is a local public-data assessor. It has no credential loader, private endpoint,
order sender, activation flag or installed scheduler. It cannot grant money authority.
The pinned research ref is `d6ed8126c041969de0bc6191e39fefe4a1272d5b`.
Research judge, universe, signal, seven-day hold and 12bps benchmark remain frozen.

## Interfaces and input contracts

Run from the canonical recovery checkout:

```sh
.venv/bin/python scripts/kity_m3_orders_off.py --help
.venv/bin/python scripts/kity_m3_orders_off.py reconstruct --bundle INPUT_BUNDLE.json
.venv/bin/python scripts/kity_m3_orders_off.py assess --signal SIGNAL.json --execution EXECUTION.json
.venv/bin/python scripts/kity_m3_orders_off.py compare-forward --bundle INPUT_BUNDLE.json --forward-dir EXTERNAL_WEEK_DIRECTORY
```

The pure Python interfaces are `reconstruct_signal(bundle, now_ms)`,
`assess_execution(signal, execution, now_ms)` and `reconcile_paper_events(signal, events, prepared)`
in `bot/kity_m3_orders_off.py`. Tests supply complete synthetic input examples.
Reconstructed signal and execution receipts retain their complete raw bundles.
Downstream validation independently rebuilds the decision; rehashing a modified
date, source clock, basket or prepared quantity cannot make it authoritative.
CLI evaluation uses its actual local clock; replay may explicitly pass a recorded
clock to the pure functions and is retrospective evidence, not a new live observation.

Every capture has exactly `venue`, `endpoint`, `params`, `request_ms`, `receive_ms`,
`raw` and `sha256`. Venue is BINANCE/BYBIT, raw is the unmodified UTF-8 response,
and SHA256 is over those bytes. Public GET captures retain local request/receive
times; hashes prove consistency, not selected-account truth or external origin.

The signal bundle contains `day`, `research_ref`, `census`, `oi` and `klines`.
`oi` is a symbol→capture mapping covering the whole eligible census; `klines`
covers every independently selected top50 symbol. OI requests use exact `symbol`,
`period: "5m"`, `endTime: cutoff_ms`; the retained response must contain exactly
one point at d−1 23:55UTC. Candle requests use `interval: "1d"`, `endTime: d_start_ms−1`.
Sixty unique contiguous closed bars and the d−1 feature are required for mature
names. Known new listings may be feature-ineligible after top50 selection.

The public census convention is a source-bound exchangeInfo capture received
within two seconds before the cutoff. This is a contemporaneous point snapshot,
not proof reconstructed from today's active list. Ambiguous relevant listing
status, incomplete OI, a missing exact point or malformed candles block the
decision. Do not substitute 23:50, rank only successful replies, pad smaller
deciles or change the source to obtain ten names. Frozen n//10 gives 3/4/5 names
per side for n=30/40/50. Owner-approved October5 correction accepts exact6/8/10 legs; no padding. See KITY_M3_CARDINALITY_CLOSURE_2026_10_05.md/JSON.

The execution bundle contains `venue`, `instruments`, exactly2k `books`,
`clock_uncertainty_ms`, `per_leg_notional_usdt`, `max_gross_notional_usdt`, optional
Binance `funding_info`, and optional `scenario_costs`. Sizing numbers are explicit
diagnostic proposals, not authenticated account caps. Quantity floors to the
step; minimum/depth/gross-cap failures reject the whole basket. Diagnostic
minimum ceilings are labelled NOT_ADMITTED_QUANTITY. The reference target is
not a hard per-leg cash or loss cap; measured VWAP and rounding residuals are
reported and real policy/tolerance remain unknown.

Assess all2k books at one retained clock. Binance matching timestamp T and
Bybit CTS are required; publication ts or quiet-market claims cannot replace
them. Source age plus supported declared clock uncertainty and receive-to-use
age must fit the unchanged 2000ms gate. Current instruments/funding metadata
must be no older than 60 seconds. Missing Binance fundingInfo entries remain
UNKNOWN; do not guess an eight-hour default.

Synthetic cost inputs require `basis: "DECLARED_SYNTHETIC"`, `source_sha256`,
`entry_fee_rate`, `exit_fee_rate`, `funding_rate_envelope` and `settlements`.
Known settlement intervals constrain the seven-day count. Exact notional weights
are used; current mark-neutral exit depth and constant funding assumptions are
not future fills, future hard bounds or selected-account fees. Funding event cash
in synthetic replay is signed. Missing account fee/reserve inputs stay blocked.

## Public capture and immutable storage

Create only the separate local KITY directory; do not use Claude's writer or
Alpaca/ATT1 runtime. Capture output is create-exclusive directly inside this root.

```sh
mkdir -p .private/kity_m3_orders_off
.venv/bin/python scripts/kity_m3_orders_off.py capture --venue BINANCE --endpoint /fapi/v1/time --params '{}' --output .private/kity_m3_orders_off/clock-UNIQUE_CAPTURE_ID.json
```

Public collection is bounded to allowlisted GET endpoints, ten-second request
timeouts and 2MiB response bodies; redirects and private parameters are rejected.
There is no service deployment in this delivery. The cutoff census and complete
OI/kline bundle producer still need operational source retention before October8.
Claude's existing derived files alone do not satisfy that contract.

Publish accepted signal decisions only inside `.private/kity_m3_orders_off` or
`runtime/kity_m3_orders_off`, using the CLI `publish` command. The exact wrapper
fields are `identity`, `day`, `research_ref`, `request_digest`, `status`,
`orders_allowed`, `money_ready`, `signal`. Identity is exactly `signal-YYYY-MM-DD`;
request digest is the pure core `digest(source_bundle)`; signal is the complete
independently reconstructed receipt. Status must match its BLOCKED_DATA or
BLOCKED_EXECUTION result; both money flags must be false. Arbitrary aliases or
generic READY_FOR_CANARY receipts are refused.

Atomic publication uses one file lock, fsync and create-exclusive linking. The
envelope hashes both receipt and seal; actual sealing time is measured internally.
The seal is the authoritative prospective eligibility result. Reconstruction's
eligibility flag describes input availability only, explicitly NOT_SEALED. Late
publication is retained as diagnostic; it cannot backdate eligibility. Identical
replay returns the original seal and file; conflicting/tampered/symlinked/incomplete
files fail closed. Input/published file bounds are 2MiB; a larger complete bundle
must receive an explicit data blocker, never be silently truncated.

```sh
.venv/bin/python scripts/kity_m3_orders_off.py publish --receipt SIGNAL_WRAPPER.json --runtime .private/kity_m3_orders_off --identity signal-2026-10-08
```

Synthetic replay requires the exact prepared public execution receipt, revalidated
from its raw execution bundle. Every event binds day, signal_hash, venue, intent_id
and prepared_digest. Entries cannot exceed prepared quantities. Exits, signed
funding (settlement ID, quantity, mark, rate, cash), fees/rebates and finality are
accounted separately. Replay returns signed exposure, realized/net cash and known
prefix state if a later event fails. A flat partial basket is exposure_reconciled,
but is not a completed intended basket. These are synthetic assertions, never
prospective terminals or authenticated broker finality.

## First unseen week and acceptance

For d=2026-10-08, retain the cutoff census at October7 23:55UTC and exact OI for
that time. Reconstruct only after October8 00:05UTC with closed d−1 candles.
Both actual input availability and immutable signal sealing must precede
October9 00:00UTC. Late reconstruction is retrospective diagnostic only and
cannot repair a missed prospective week. Paper entry/exit close references
become available October9/October16 00:05UTC; they are not executable fills.

Independently reconstruct the expected basket before comparing external Claude
signal.json and hashed `syroe` files. Read/validate those files only: never run
Claude `--shag`, change his ref, rerun the judge or start a second forward writer.
Missing ref/raw wire evidence yields BLOCKED_DATA even when symbols agree.

Valid public arithmetic still returns BLOCKED_DATA until selected venue/account
fees, cash/margin/mode, absolute portfolio/per-leg/daily risk caps, rounding
tolerance, funding reserve, concurrent ownership, partial-basket unwind,
protection/exit/finality and rollback dossier are source-bound and reviewed.
Bybit additionally needs actual-basket Binance→Bybit price/funding portability.
No public PASS is READY_FOR_CANARY or owner GO.

## Existing production and next work

Alpaca state and ATT1 probes are untouched. The original ATT1 deadline remains
October6 14:12:25UTC; its independent 2–3 clean terminal/net-R gate, actual dossier
and separate owner GO remain. Operational Alpaca followup is October6 re-arm,
AMD delayed fees and a separate PAPER queued DAY-stop test.

Claude's useful parallel delivery is raw causal/atomic forward evidence,
machine-readable frozen registry/test vectors and runtime provenance. Then one
independent LONG mechanism, followed by one RANGE mechanism through Factory,
WIP1. Include cost/minimum/PIT feasibility before expensive research and preserve
frozen falsification/holdout; no broad architecture rewrite or signal retuning.
