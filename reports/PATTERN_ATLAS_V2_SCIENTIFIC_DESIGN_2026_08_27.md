# Pattern Atlas v2 — scientific market-morphology design

**Status:** `DRAFT_FOR_PREREGISTRATION`; discovery-only; no live, broker,
promotion, sealed-release, or parameter-tuning authority.

## Why this experiment exists

Pattern Atlas v1 already measured 20,372 causal paths on a hash-pinned 13-symbol
cohort. It tested six horizontal-level hypotheses and retained only one bounded
successor question: `horizontal_breakout_long` at 72 hours. That successor later
received `NO_PROMOTION`. V2 must therefore answer a different question: not
"which indicator wins?", but **which causal market morphologies recur, how long
they last, and when breakout/retest/rejection behavior differs from matched
random time**.

This is a descriptive atlas, not a trading strategy. It cannot justify capital
or a new live sleeve. Any successor must be frozen as a separate exact execution
contract before another dataset is read.

## Fixed evidence contract

- Development evidence: the exact prefix addressed by
  `configs/preregistered/event_long_dev13_uniform_m5_window_v1_20260714.json`
  (`16b4f746...facfb`) and the v1 contract (`9e4b1660...d0551`). The old 120-day
  tail must not be used to invent or tune V2 bins. These are draft references;
  the machine prereg must record full hashes before any V2 run.
- Physical sides remain separate.
- Features at decision time may use only completed H1 bars.
- Entry anchor for forward paths: next H1 open.
- Fixed forward horizons: 6h, 24h, 72h, 168h, 336h.
- Same-family observations on one symbol must not overlap at the longest horizon.
- Controls: 20 deterministic draws per event from the same symbol, side, UTC
  month, volatility bucket and causal regime. Seed is
  `SHA256(config_fingerprint || event_id || draw_index)`. Draws are without
  replacement within an event; event windows and any control whose forward path
  overlaps the event are excluded; cross-event reuse and collision counts remain
  visible. An unavailable future/path is `pending`, never silently dropped.
- Report base distributions first. Costs, fills, stops, sizing, and portfolio
  overlap are explicitly outside this atlas.

## Fixed morphology families

The bins below are physical definitions, not values to optimize after seeing the
output.

| Family | Causal measurement | Fixed buckets |
| --- | --- | --- |
| Impulse length | consecutive same-direction H1 closes ending at decision bar | `1`, `2`, `3`, `4+` bars |
| Impulse size | close-to-close impulse divided by causal ATR(24) | `<1`, `1–2`, `2–3`, `>=3 ATR` |
| Horizontal breakout distance | close beyond prior-20-H1 extreme / ATR(24) | `0–0.25`, `0.25–0.5`, `0.5–1`, `>=1 ATR` |
| Level age | hours since the causal prior-20 extreme was first printed | `1–6`, `7–24`, `25–72`, `73+` |
| Prior touches | completed H1 bars touching the level within 10 bps before the event | `1`, `2`, `3+` |
| Retest delay | completed H1 bars from breakout to first causal retest within 10 bps | `1`, `2–3`, `4–12`, `no retest by 12` |
| Retest depth | penetration through the level / ATR(24) | `none`, `0–0.25`, `0.25–0.5`, `>0.5 ATR` |
| Rejection geometry | directional wick divided by `max(abs(close-open), close*1e-12)` | `1–1.5`, `1.5–2.5`, `>=2.5` |
| False break | price crosses level and closes back through it | long/short as separate hypotheses |
| Range maturity | causal width of prior-20 range / ATR(24) | `<3`, `3–6`, `>6 ATR` |

Order blocks and imbalances are intentionally a **separate family**. They may be
joined only after the existing order-block detector has a point-in-time event
passport and a non-overlap/control engine. V2 must not silently import the old
overlapping order-block measurements.

Event anchors are family-specific. A breakout path starts at the open after the
completed breakout bar and contains no future retest feature. A retest path starts
only at the open after the completed retest bar. `No retest by 12` becomes known
only at the close of bar 12, so its path starts at bar 13. Unit tests must prove
that appending bars after each decision anchor cannot change its feature vector.

## Causal regimes

Every event and control is labelled, never filtered after the fact:

1. `bull_trend`: close above causal EMA200 and EMA200 slope over 24 H1 bars > 0;
2. `bear_trend`: close below causal EMA200 and EMA200 slope < 0;
3. `bull_chop`: close above EMA200 without positive slope confirmation;
4. `bear_chop`: close below EMA200 without negative slope confirmation;
5. `unknown`: insufficient warm-up — visible but excluded from conclusions.

BTC and ETH must be reported as fixed standalone cohorts in addition to the full
cohort. They are diagnostic strata, not post-hoc exclusions or a permission to
give them custom parameters.

## Outputs

For every predeclared cell:

- `N`, mean/median/p25/p75 forward return;
- hit rate, MFE, MAE, time-to-MFE, time-to-MAE;
- excess versus deterministic matched control;
- per-symbol count and mean, largest-symbol share (`max symbol N / cell N`), HHI;
- chronological halves and leave-one-symbol-out stability;
- result with the top 5% absolute outcomes removed;
- overlap count and missing/unknown feature count.

The report must preserve empty, negative, concentrated, and unstable cells. No
single ranking score is allowed.

## Multiple-testing boundary

The full matrix is descriptive and **may nominate no successor from this same
evidence**. The machine prereg must either declare at most two primary cells and a
FWER/FDR rule before execution, or treat every cell as hypothesis generation only.
Any visually interesting cell becomes a new preregistered question tested on
untouched/prospective evidence; it cannot be promoted by the atlas result itself.

## Build order and fail-closed receipts

1. Implement pure feature functions and unit tests on hand-built bars.
2. Pin the exact input manifest, aggregation code, runner, config, and Python
   dependency hashes.
3. Run integrity-only: prove the loader stops before excluded rows and that every
   feature is invariant to appending future bars.
4. Run the bounded discovery once through Research Station v3.
5. Independently recompute counts, arithmetic, overlap, concentration, and
   control matching.
6. Publish the immutable receipt and only then review possible successors.

## Work allocation

- Deterministic Python: loading, hashes, causal features, controls, metrics,
  invariants, independent audit.
- Ollama: classify logs, summarize already materialized cells, flag suspicious
  concentrations or missing explanations. It cannot execute a promotion, choose
  bins, rewrite code, or alter the frozen conclusion.
- Strong model review: causal leakage, control design, multiple-testing, and the
  final decision about whether a successor experiment is scientifically valid.
