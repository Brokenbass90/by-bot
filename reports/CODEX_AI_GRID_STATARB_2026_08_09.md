# AI context, FX grid V2 and pair stat-arb V2 — 2026-08-09

## Outcome first

- The VPS live mirror completed atomically at `2026-08-09T05:10:54Z` with
  33 files synced, two non-critical files absent, and zero transfer failures.
- Ollama's claim that the live AI context was 10.8 days old was a false positive:
  the auditor inspected the obsolete local path `runtime/ai_context/full_context.json`
  instead of the authoritative mirror
  `runtime/live_mirror/ai_context/full_context.json`.
- FX smart-grid V2 is structurally safer but too sparse: the selected stress arm
  has five trades only. It is not evidence of positive economics.
- Pair statistical arbitrage V2 is broadly negative after two-leg costs and is
  closed in its current form.
- Neither research result has live authority or changes live risk.

## What Ollama sees

The local chat does not and must not ingest the whole repository. It receives a
bounded allowlist of status reports and verdicts, plus a deterministic fact index.
This prevents secrets, broker credentials, arbitrary dirty WIP, and stale prose
from being treated as live truth. Free-form model answers remain proposal-only;
`/status` is the deterministic status surface.

The allowlist now includes the atomic VPS mirror manifest and both V2 research
verdicts. The structural auditor now checks the authoritative mirror path rather
than the obsolete local cache path.

## FX smart-grid V2

Implemented in `research_lab/fx_smart_grid_v2.py` as a separate architecture:

- equal-sized layers only; no martingale;
- trailing train range, width/efficiency/drift gates;
- alternating boundary touches;
- breakout cooldown and emergency whole-grid kill;
- directional volume-spike and session gates;
- public OANDA proxy costs and four chronological folds;
- 32 logged trials.

Initial bounded result:

- stress trades: 5;
- stress net: +64.63 bps;
- PF: 4.294;
- positive chronological folds: 3/4;
- dominant rejection: range width, 65,477 bars;
- decision: `FAIL_OR_REBUILD` because N is far below 100 and the cost contract is
  expired for promotion.

Interpretation: the rules are safer, but the candidate is over-filtered. The next
experiment must be explicitly preregistered as a liveness calibration; the five
trades cannot be promoted or annualized.

## Pair stat-arb V2

Implemented independently of Claude's path-broken prototype:

- repository-relative data paths;
- 20 symbols and 190 candidate pairs;
- rolling train-only OLS hedge ratio;
- residual AR(1) stationarity proxy;
- chronological folds;
- two-leg costs;
- pair and profit-concentration measurements;
- 16 logged trials.

Initial result:

- 756 trades;
- aggregate net: -76,572 bps;
- PF: 0.7515;
- win rate: 50.4%;
- positive folds: 2/4;
- positive pairs: 88/181 traded;
- best-pair positive contribution: 5.51%;
- decision: `FAIL_OR_REBUILD`.

Interpretation: this is not a single-pair concentration accident. The simple
daily residual-reversion family is negative after costs. A later formal
cointegration experiment may be justified, but this V2 is closed.

## Fresh live state at mirror time

- money sleeve: ATT1 only, risk multiplier 0.10;
- one broker position: ADAUSDT short, exchange stop present;
- BOUNCE1: enabled in shadow at risk 0.0;
- BOUNCE1 liveness: 1,347 attempts, 1,347 no-signal outcomes, zero decisions;
- market regime: `bull_chop`.

The BOUNCE1 blocker is therefore liveness, not insufficient trade count. It needs
a blocker-distribution audit before any threshold change.

## Next falsifiable gates

1. Produce a BOUNCE1 blocker-distribution report and compare live and exact
   backtest predicates without changing live thresholds.
2. Preregister a crypto consolidation-exit/level-impulse V1 based on the owner's
   stated idea: impulse only after an established balance, with separate long and
   short context and executable costs.
3. Preregister FX grid V2b as liveness calibration only; any changed structural
   gate must be frozen before untouched OOS.
4. Keep pair stat-arb V2 closed; formal cointegration is a separate, lower-priority
   hypothesis.

## Accepted and rejected grid recommendations

Accepted: regime gate, alternating boundary touches, range age, breakout cooldown,
session/spread gate, and emergency whole-grid kill.

Rejected: increasing size after losses, waiting indefinitely for breakeven, and
hedging a broken grid with another correlated pair. Those mechanisms hide or
compound risk rather than create edge.
