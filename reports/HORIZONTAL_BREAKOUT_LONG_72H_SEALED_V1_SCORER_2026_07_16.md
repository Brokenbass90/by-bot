# Horizontal breakout long 72h: final sealed verdict

## Technical summary

The only authorized 120-day sealed performance run is complete.  The frozen
`horizontal_breakout_long_72h_v1` candidate receives **NO_PROMOTION**.

This is a useful negative result, not an infrastructure failure.  All 13 price
sources and all 13 funding histories passed integrity checks; 155 valid trades
were scored, with zero invalid or censored trades.  The candidate failed before
costs and deteriorated further under the frozen base and stress execution
contracts.  No shadow/live permission was created and no real order or broker
call occurred.

The one-shot attempt is consumed.  Retrying, filtering the losing symbols or
folds, rescuing TAO, or tuning parameters against this holdout is prohibited.

## Dataset and grain

- Candidate: exactly one physical long, no short logic.
- Signal: a completed H1 bar opens at or below the maximum high of the prior 20
  completed H1 bars and closes strictly above that frozen level.
- Fill: next H1 open with adverse long slippage.
- Exit: close of the 72nd completed H1 after entry; no stop, target, trailing,
  retest, regime, volume, momentum, or AI filter.
- Cohort: 13 frozen Bybit USDT perpetual symbols.
- Holdout: 6 March 2026 14:00 UTC to 4 July 2026 14:00 UTC, end-exclusive.
- Evidence decoded: 449,280 sealed M5 rows plus exactly 20 completed H1 warmup
  bars per symbol, aggregated to closed UTC H1.
- Funding: 6,400 hash-pinned public Bybit events across 32 raw API pages.  Eight-
  hour symbols have 360 in-window events; ONDO, TAO and WIF use actual four-hour
  histories with 720 events.
- Portfolio simulation: fixed $769.23 notional per trade, $10,000 initial
  equity, no compounding or leverage, maximum one position per symbol.

## What the sealed evidence says

| Metric | Discovery lead | Sealed gross | Sealed base | Sealed stress |
|---|---:|---:|---:|---:|
| Trades | 909 | 155 | 155 | 155 |
| Mean return | +54.5 bps | -159.2 bps | -179.4 bps | -244.2 bps |
| Median return | -49.2 bps | -155.1 bps | -176.9 bps | -230.6 bps |
| Win rate | 48.0% | 32.3% | 31.6% | 24.5% |
| Profit factor | descriptive only | not gated | 0.392 | 0.281 |

The discovery result was a fat-tail sample: its positive mean coexisted with a
negative median.  In untouched data both mean and median became strongly
negative.  The raw sealed mean of -159.2 bps proves that fees and funding are
not the root cause; the selected directional pattern itself did not generalize.

Base funding debit averaged 4.27 bps per trade and total base non-funding
friction was approximately 16 bps.  Stress funding averaged 55.16 bps because
the preregistration charges at least 5 bps at each actual settlement event;
stress round-trip non-funding friction was approximately 30 bps.

The fixed-notional simulation lost $2,139.35 under base costs and $2,911.81
under stress costs.  These are research-simulation values, not real account
losses.  The timestamp-marked stress maximum drawdown was 36.90%, above the
frozen 12% ceiling.

## Fold, breadth and concentration result

| Fold | Trades | Stress net, summed bps | Stress PF |
|---|---:|---:|---:|
| Fold 1 | 49 | -10,586.5 | 0.343 |
| Fold 2 | 39 | -4,623.9 | 0.529 |
| Fold 3 | 32 | -12,473.0 | 0.121 |
| Fold 4 | 35 | -10,170.2 | 0.188 |

All four folds lost money.  All 13 symbols traded, but only TAO was positive
under stress (`N=12`, PF 1.463).  That single post-hoc pocket cannot be promoted:
the contract requires at least seven positive symbols, positive leave-one-
symbol-out results, and forbids excluding symbols after the holdout is viewed.

Trade-count breadth itself was healthy: largest-symbol share was 8.39% and HHI
was 0.0774, both within their ceilings.  Therefore the rejection is not caused
by one symbol dominating the sample; losses were broad.

## Frozen gates

Passed:

- 155 stress trades versus minimum 100;
- at least 15 trades in every fold;
- 13 traded symbols versus minimum 10;
- long-side purity 100%;
- zero invalid/censored trades;
- trade-count share and HHI concentration limits.

Failed:

- base PF 0.392 versus minimum 1.25;
- stress PF 0.281 versus minimum 1.10;
- stress net and 95% winsorized mean both negative;
- stress drawdown 36.90% versus maximum 12%;
- zero positive folds versus minimum three;
- one positive symbol versus minimum seven;
- positive-PnL concentration and every LOSO profitability gate.

## Integrity and lookahead controls

The original preregistration, uniform price manifest, aggregation code, scorer,
READY authorization, funding manifest and every raw funding page were hash-
pinned before price access.  The READY preflight returned
`PERFORMANCE_RESEARCH_ALLOWED`, `blockers=[]`, 13/13 complete funding histories,
zero market snapshots and zero decoded sealed rows.

The scorer then created `run_claim.json` directly with exclusive creation before
opening the first price snapshot.  Two concurrent processes cannot both claim
the holdout.  Entry uses the next H1 open, exit uses the 72nd completed H1 close,
the first 72 completed closes after each internal boundary are embargoed, and
cooldown state continues through folds and embargoes.

Stress timestamp drawdown marks positions from the entry timestamp and assumes
immediate adverse liquidation, including both fees, both slippage legs and all
funding settled through each mark.  An independent reviewer confirmed these
boundaries and calculations before the run.

## Data-quality findings

The earlier blocker is resolved.  A public-only resumable builder paginated
backward with Bybit `endTime`, persisted every raw response before advancing its
checkpoint, and replay-validated hashes and cursor continuity.  It used no API
key, private endpoint, price snapshot, broker, live runner or order method.
The pagination contract follows Bybit's official
[Funding Rate History](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate)
endpoint: an `endTime`-only query returns up to 200 prior settlements, while
funding intervals are symbol-specific.

The completed funding manifest contains 13/13 symbols, 32 raw pages and 6,400
events.  Each symbol brackets both holdout boundaries, actual four/eight-hour
intervals are retained, and no unexplained gap exceeds eight hours.  A failed
candidate manifest is validated before the immutable final filename can be
published.

## Decision and next action

1. Retire `horizontal_breakout_long_72h_v1` as a promotion candidate.
2. Preserve the receipt and all 155 trades as negative evidence for the
   hypothesis ledger.
3. Do not create a TAO-only, altered-cooldown, regime-filtered, shorter-hold or
   cost-relaxed variant from this same holdout.
4. A genuinely different successor requires a new named preregistration and
   new unseen future data.  The observed failure suggests prioritizing a
   different causal mechanism rather than parameter repair of prior-20 H1
   breakouts.

Pattern Atlas was not wasted: it generated a bounded hypothesis, and the sealed
gate prevented a non-generalizing discovery pocket from reaching money.  That
is exactly the behavior the research system was built to provide.

## Reproducibility evidence

- Strategy config SHA: `44c8d35a5bae734be0bb47f2bd2ea81cc82c13eac4b8e19356e802350fd6a04a`
- Scorer SHA: `1e74cff0cbbad2cc73eb51597a2959fc543287d0156a0464c123895ec99f9f9f`
- READY authorization SHA: `d528437b1e0812038903b7fcc2f664939ce469f44b05169c1bdc6b0e0e7b3979`
- Funding manifest SHA: `c10525b0a1111664235e5b5d471813cd7bb9ff249cce31e472ed61da0382292f`
- One-shot claim SHA: `e52c0f8a8ced6f68a38935f84a46b10c2cbee832df5d2c11170fcda188694787`
- Trades SHA: `5d972a2f841fa486be519c210d69b6a4744ea63486cea63cdab53de2518de7cd`
- Final receipt SHA: `d735ad0b05a752a36a3e11932d119962fbb8f0a8ac584a55eaa1d2771edcaa97`
- Focused scorer/materializer/preflight suite: 26 tests passed before the run.
- Full project regression after the run: 1,398 tests passed.
- Live deployment, allocator change, broker call or order: none.
