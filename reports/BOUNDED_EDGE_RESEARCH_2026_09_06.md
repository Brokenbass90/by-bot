# Bounded Edge Research — 2026-09-06

## Technical summary

This memo proposes three small, independent research tracks that can run beside
the unchanged ATT1/ETS2S L1 burn-in. None of them changes the deployed release,
adds authority, reads private data, or makes a trading or promotion claim.

- **Execution replay:** shortlist hftbacktest and NautilusTrader. Use a tiny
  public-data fixture to test L2/L3 execution semantics, with hftbacktest as
  the specialist for L2 queue/latency replay and NautilusTrader as the broader
  lifecycle/event-ordering comparator.
- **Funding/basis:** run one public-only cash-carry net-cycle screen using the
  frozen Bybit v2 contract already present in the tree. Preserve equal economic
  assumptions, common base quantity, walked depth, no basis-convergence credit,
  and fail-closed refusal. A pass is review-only evidence; it cannot promote
  the strategy or delay P0.
- **Market Perception:** first create a cheap, leakage-safe event table and
  compare majority/climatology, deterministic state, logistic, empirical
  nearest-neighbour, and random-ranking controls. Measure classification,
  cross-sectional ranking, analogue similarity, and probabilistic forecast
  quality chronologically. A Market Perception adapter has its own project
  gates; the LAB_AI researcher-adapter label threshold is not copied here.

The acceptance gates below are deliberately stronger than an aggregate positive
number: failures in time ordering, source freshness, costs, symbol breadth,
calibration, or lifecycle parity terminate the candidate or leave it
`INCONCLUSIVE`. No result in this memo is an edge estimate.

## 1. Execution replay candidates for L2/L3 parity

### Candidate A — hftbacktest

[HftBacktest's official documentation](https://hftbacktest.readthedocs.io/en/py-v2.3.0/)
describes tick-by-tick replay, L2/L3 book reconstruction, feed and order
latency models, and queue-position-aware fills. Its [order-fill contract](https://hftbacktest.readthedocs.io/en/latest/order_fill.html)
also states that replay does not let simulated orders change the historical
market and that some liquidity-taking partial fills can therefore be
unrealistic.

**Fit for this station.** Use it only for a public Bybit depth/trade fixture
when the question is whether resting orders, latency, queue position, and
partial/non-fill assumptions materially change the L2 execution ledger. Keep
the fixture small and require a source manifest containing the exact feed
format, timestamps, symbol, tick/lot metadata, and replay hash.

**Binding limitation.** A positive replay result can be a fill-model artifact:
the historical book is immutable and the queue model is estimated for
Market-By-Price data. It is therefore a parity instrument, not a profitability
proof. This interpretation is an inference from the documented simulator
scope and the project's requirement for independent execution and cost parity.

### Candidate B — NautilusTrader

[NautilusTrader's official documentation](https://nautilustrader.io/docs/)
positions the engine as event-driven infrastructure spanning research,
deterministic simulation, portfolio/risk modelling, and live execution. Its
[backtest execution flow](https://nautilustrader.io/docs/latest/concepts/backtesting/execution-flow/)
specifies exchange processing before strategy callbacks, command settlement,
latency-delayed commands, funding-rate settlement points, shutdown drain
semantics, and deterministic simulated trade IDs.

**Fit for this station.** Use it as the lifecycle comparator for L2/L3:
signal admission and deduplication, order-plan creation, partial/non-fill
handling, stop/TP/trailing/time-stop transitions, funding settlement, restart
reconciliation, and terminal exits. A thin adapter should map the project's
hash-bound public observation and execution ledger into the engine without
replacing the canonical ledger.

**Binding limitation.** The engine's richer event semantics do not repair
missing source data, account-specific fees, or the project's existing
instrument and broker contracts. The adapter must prove byte-stable decisions
on fixtures before any larger replay. This is an inference from the documented
event model and the checkpoint's L2/L3 parity gate.

### Recommended bounded comparison

Do not install either package in this task. Prepare one synthetic semantics
fixture with at most 2 symbols, 1,000 market-data events per symbol, one signal
lifecycle per symbol, one synthetic funding settlement, one partial/non-fill
refusal, one restart, and one terminal exit. This fixture is sufficient to
compare lifecycle and arithmetic semantics; it is not evidence of realistic
funding, depth, queue, or market replay behaviour. Run the same canonical
input through the existing pure ledger and each candidate when the fixture
and ordinary bounded-research storage guards are ready.

Acceptance for the replay comparison:

1. Under one explicitly shared fill, fee, rounding, funding, and timestamp
   assumption set, every engine agrees with the canonical ledger on admission,
   arithmetic, exposure, exit, and terminal-state facts, or each difference
   has a typed, reviewed explanation.
2. Fill-model outputs are compared separately as sensitivity analysis. Different
   queue, latency, or partial-fill models are not required to produce equal
   fills; their assumptions and resulting deltas must be reported.
3. Replaying the same fixture twice yields the same serialized decisions and
   event identities.
4. A deliberately stale/skewed input, invalid quantity, missing funding mark,
   partial fill where forbidden, and restart corruption each fail closed.
5. No engine call can reach private APIs, orders, risk controls, deployment, or
   the money runtime.

Death criteria:

- Any unexplainable shared-contract lifecycle divergence, nondeterministic
  replay, or silent partial fill kills the adapter.
- Any result that depends on full-book history unavailable in the canonical
  public tape is `BLOCKED_DATA_OR_PARITY`, not an estimate.
- A simulator that only produces attractive PnL without proving the above
  parity gates is discarded for this use.

Budget: one fixture, no network acquisition, no package installation in this
memo; future local comparison capped at 2 CPU-hours, 4 GiB RAM, and 1 GiB of
temporary input/output. These are proposed research limits, not measured
resource use.

## 2. One bounded funding/basis experiment

### Experiment: public cash-carry v2 net-cycle screen

Reuse the frozen `bybit_cashcarry_shadow_v2_20260715` and
`public_cashcarry_station_v1_20260716` contracts. The experiment is a
public-only, same-exchange construction: long spot plus short USDT linear
perpetual, equal USD target per leg, positive funding where the short receives.
The exact local contracts are the source of truth; no historical outcome or
sealed result is opened for this memo.

Frozen mechanics and cost inputs:

| Item | Contract |
|---|---|
| Symbols | BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT, SUIUSDT |
| Observation | public GET only: instruments, orderbook, tickers, funding history |
| Funding admission | at least 3 distinct completed positive settlements; use the minimum of projected and required completed rates |
| Fees | spot 10 bps per fill; linear perp 5.5 bps per fill |
| Slippage | adverse 2 bps per fill in the v1 mechanics contract |
| Basis reserve | 10 bps adverse basis stress; no convergence credit |
| Residual edge | at least 5 bps after two spot fees, two perp fees, walked spread/slippage, and basis reserve |
| Quantity/depth | common base quantity floored to the least common step; deterministic multi-level walk; both minimums must pass |
| Refusal | stale/skewed/missing/crossed state, insufficient depth, or forbidden partial fill means observe-only/no state mutation |
| Station bound | 7 days, 1,800 second poll, 50 book levels, 2,304 observations, 512 MiB total, 85 GiB minimum free space |

The [official Bybit funding-history endpoint](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate)
documents symbol-specific funding intervals, the linear/inverse categories,
the funding rate and settlement timestamp fields, and the public
`/v5/market/funding/history` request. This supports the timestamped public
input path; it does not establish executable profitability. Bybit's funding
interval and current contract metadata must remain sourced from the relevant
instrument response.

### Measurement and acceptance

For every candidate cycle, retain a checksummed observation, decision, four-leg
paper lifecycle, funding receipts only for settlements strictly after entry,
executable basis path, and terminal status. Report net cycle PnL only after all
configured costs and basis stress. Split results by symbol and chronological
window; never annualize a short screen.

The screen is reviewable only if all of the following hold:

1. At least 10 completed cycles reproduce mechanics and restart/idempotency
   behavior without exception.
2. At least 30 completed cycles span at least 3 liquid symbols.
3. Median and p25 net cycle results are positive under both base and stress
   costs, with no single-symbol result carrying the decision.
4. Every cycle has complete funding timestamps, quote-age/skew checks,
   quantity/lot metadata, walked depth, and an all-in fee record.

Any missing settlement mark, incomplete source coverage, basis attribution
gap, partial-fill ambiguity, or account-tier mismatch is a fail-closed blocker.
The contract's `NO_ENTRY`/observe-only outcome is correct evidence when the
cost and funding requirements do not clear; it is not a failed trading signal.

If fewer than 30 completed cycles or fewer than 3 symbols are available, the
binding classification is `INCONCLUSIVE_LOW_N`: do not call it a killed edge,
positive edge, or promotion result. Continue only if a separately bounded
collection can satisfy the frozen contract. Once the minimum sample is met,
non-positive p25 or median under stress, a symbol concentration that explains
the result, or any fabricated/missing funding cash flow is a death condition.
These thresholds are inferred from the frozen local evidence gates and are
research classifications, not exchange rules.

Budget: reuse the existing 7-day station cap; no new data acquisition is
performed in this task, no private API, account state, order, daemon,
deployment, or capital is allowed, and no old `$5–15/month per $1,000`
forecast is admissible.

## 3. Cheap Market Perception baseline before LoRA

Market Perception remains a separate research project with the planned flow
`Market State -> Pattern Memory -> Regime/Drift -> Strategy Experts -> Meta
Gate -> Shadow`. The [LAB_AI_V0 design](../docs/superpowers/specs/2026-09-06-lab-ai-v0-design.md)
keeps the first adapter focused on research quality and explicitly defers a
price-prediction LoRA. The design below is the cheapest independent baseline
that can test whether the Market Perception question is measurable at all.

### Event table and causal split

Create one row per eligible setup at decision time `t` from already available
closed-bar/state data. Store `symbol`, `setup_id`, `decision_ts`, source SHA,
timeframe, regime features, normalized returns/volatility/range, level/context
features, funding if present before `t`, and the exact next-observation
availability timestamp. Do not include any field computed from bars at or
after the label horizon.

Use four expanding chronological development folds and one untouched final tail
of at least 20%. Apply an embargo at least as long as the maximum forecast
horizon and group overlapping events so one price path cannot appear in both
train and test. Add leave-one-symbol-out checks when the symbol count supports
it. The [scikit-learn `TimeSeriesSplit` documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
confirms why ordinary random cross-validation is unsuitable: it can train on
future observations and evaluate on past observations; its `gap` parameter is
available to exclude a boundary region.

### Four outputs, each with a cheap baseline

| Question | Label/output | Baseline first | Metric |
|---|---|---|---|
| Classification | `FAVORABLE`, `NEUTRAL`, `ADVERSE` forward path using fixed horizon and pre-registered risk/cost thresholds | majority/climatology, then scaled logistic regression | macro-F1, balanced accuracy, Brier score, calibration by fold |
| Cross-sectional ranking | rank eligible same-timestamp setups by realized cost-adjusted forward score | deterministic state score and hash-seeded random ranking | NDCG@k, top-k hit rate, Spearman rank correlation |
| Pattern similarity | nearest historical states using features known before `t` | random neighbour and same-regime historical median | analogue outcome MAE, calibration/coverage, neighbour stability |
| Forecast hypothesis | probability of each class plus median and lower/upper return quantiles | empirical regime-conditioned probabilities/quantiles; ridge or isotonic calibration only if needed | log loss, Brier, pinball loss, reliability error |

The labels are for research measurement only. A “favorable” label is a
forward outcome category under a fixed path/cost contract, not a trade
instruction. Ranking is evaluated within a timestamp, never by sorting future
outcomes during feature construction. Similarity must fit scaling and
neighbour indexes on past data only. Forecast intervals must be scored for
coverage and sharpness, not just average return.

### Hypotheses to preregister

These are falsifiable hypotheses, not claims:

1. Regime-conditioned classification beats the majority baseline on the final
   tail without losing calibration or collapsing to one symbol.
2. A causal nearest-neighbour memory improves analogue error or calibration
   over same-regime medians on at least three chronological folds.
3. Cross-sectional state ranking improves NDCG@k and top-k hit rate over both
   deterministic state score and random ranking, with gains spread across
   symbols and regimes.
4. Forecast probabilities/quantiles are more reliable than the empirical
   climatology after calibration; a positive mean alone is insufficient.

### Acceptance and death criteria

Accept the baseline as a useful research component only when:

- all rows have causal feature/label availability and reproducible source
  hashes;
- the final tail is untouched until the model and thresholds are frozen;
- at least three of four development folds and the final tail beat their
  named baseline by a pre-registered margin: +5 macro-F1 points or 10% lower
  Brier for classification, +5% NDCG@k and positive rank correlation delta
  for ranking, or 10% lower analogue MAE/calibration error for similarity;
- no single symbol, regime, or event cluster contributes over 35% of the
  claimed improvement;
- the result remains directionally present in leave-one-symbol-out or a
  clearly documented `INCONCLUSIVE_LOW_N` case.

Kill the version if there is any leakage, future data in an input hash, label
availability mismatch, random-split-only improvement, failed calibration,
single-symbol concentration above 35%, or no baseline-relative improvement on
the untouched tail. If sample size cannot support the thresholds, record
`INCONCLUSIVE_LOW_N` and stop feature/model expansion.

The LAB_AI_V0 requirement of at least 500 human-reviewed training examples and
100 untouched evaluation examples applies to its separate researcher adapter.
It is not a mandatory Market Perception forecast-adapter threshold. For this
project, any learned adapter remains ineligible until the deterministic
baseline passes its chronological holdout gates, the feature/label contract is
reviewed, and a separate Market Perception evaluation set and adapter gate are
written. Any later adapter remains proposal/shadow-only and could not write
configs, alter a verdict, or receive money authority.

Budget: existing local data only; cap the first pass at 64 features, 100,000
event rows, 4 GiB RAM, 2 CPU-hours, and zero GPU/network/package installation.
No embedding index is required: exact standardized vectors and a bounded
in-memory nearest-neighbour scan are sufficient for the first falsification
pass. These limits are proposed budgets, not measured usage.

## 4. Scope, limitations, and source record

The current checkpoint dated 2026-09-06 says the ATT1/ETS2S fixed-51 L1 shadow
is inside its 72-hour burn-in, with no broker/order calls or money authority;
L2 execution lifecycle parity and L3 fees/funding/accounting parity remain
mandatory before any micro-canary discussion. This memo is intentionally
parallel and does not edit that release, checkpoint, or roadmap.

The local cash-carry contracts are dated 2026-07-15 and 2026-07-16. They are
frozen research specifications, not current account-fee receipts. The Bybit
documentation was checked live on 2026-09-06; the hftbacktest, NautilusTrader,
and scikit-learn pages were also checked live on 2026-09-06. “Fit,” “binding
limitation,” thresholds beyond the already frozen contracts, and all future
resource caps are explicit inferences/proposals in this memo.

Sources:

- [Session checkpoint, 2026-09-06](CODEX_SESSION_CHECKPOINT_2026_09_06.md)
- [Current project roadmap, 2026-09-06](CURRENT_PROJECT_ROADMAP.md)
- [LAB_AI_V0 design, 2026-09-06](../docs/superpowers/specs/2026-09-06-lab-ai-v0-design.md)
- `configs/preregistered/bybit_cashcarry_shadow_v2_20260715.json`, frozen 2026-07-15
- `configs/preregistered/public_cashcarry_station_v1_20260716.json`, frozen 2026-07-16
- [hftbacktest documentation](https://hftbacktest.readthedocs.io/en/py-v2.3.0/), checked 2026-09-06
- [hftbacktest order-fill documentation](https://hftbacktest.readthedocs.io/en/latest/order_fill.html), checked 2026-09-06
- [NautilusTrader documentation](https://nautilustrader.io/docs/), checked 2026-09-06
- [NautilusTrader backtest execution flow](https://nautilustrader.io/docs/latest/concepts/backtesting/execution-flow/), checked 2026-09-06
- [Bybit funding-rate history API](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate), checked 2026-09-06
- [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html), checked 2026-09-06

## 5. Next gates

1. Keep the deployed ATT1/ETS2S release unchanged through the 72-hour boundary
   and produce its burn-in receipt.
2. Freeze the L2/L3 canonical fixture, first compare shared lifecycle and
   arithmetic semantics, then run fill-model sensitivity against the existing
   ledger.
3. When storage guards are green, run the one bounded public cash-carry screen
   under the frozen v2 contract; low cycle or symbol count must remain
   `INCONCLUSIVE_LOW_N`.
4. Build the Market Perception event schema and baseline evaluator from
   existing local data, preregister splits/labels/metrics, and publish only a
   research receipt.
5. Block replay realism until a canonical public tape with sufficient L2 depth
   and trade coverage is identified; block Market Perception scoring until the
   forward horizon, cost-adjusted labels, and independent symbol/regime sample
   are fixed.
6. Do not install, train, acquire network data, deploy, shadow, promote, or
   allocate capital as part of this memo.
