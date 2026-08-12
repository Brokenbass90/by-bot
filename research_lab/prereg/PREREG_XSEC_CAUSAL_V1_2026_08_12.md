# PREREG XSEC causal V1 — frozen 12 August 2026

## Authority and purpose

Research-only. No broker, order, risk or promotion authority. This replay asks
whether the already-published XSEC V3+event-filter decision rule survives an
executable next-open contract and actual Bybit funding cashflows. It cannot
authorize money because the selected 137-symbol pool is current-survivor based.

## Immutable window and inputs

- Analysis: `[2023-01-01, 2025-10-01)` UTC.
- Sealed holdout: `[2025-10-01, 2026-07-01)`, must not be requested/read.
- Daily OHLC: physically isolated public Bybit archive ending exclusively at
  `2025-10-01`.
- Funding: physically isolated public Bybit archive ending exclusively at the
  same boundary.
- Universe: exact symbol filename set from the existing 137-symbol research
  inventory. This is not full historical PIT; survivorship remains a blocker.

## Frozen strategy

- Decision core: `research_lab/xsec_v3_reference.py` unchanged.
- Lookbacks `[7,14,21,30,45]`, top/bottom `K=5` per lookback.
- Maturity `390` calendar days from provider launch time.
- Both already-published V4 filters enabled: post-event noise `3 sigma`; market
  stress above the rolling 60-day 90th percentile.
- Three phases offset by one day, each with one third of sleeve capital.
- Signal uses only completed UTC daily closes through day `i`.
- Entry: next UTC daily open `i+1`; exit: UTC daily open `i+4` (three-day hold).
- Missing entry/exit open for any selected symbol: that rebalance fails closed;
  no fallback to close.
- Funding: sum every event in `(entry_ts, exit_ts]`; cashflow is
  `-weight * funding_rate`.
- Vol target and cap remain the published V3 contract.

## Cost scenarios and attempt count

One strategy variant; two predeclared cost scenarios, not a parameter search:

- base: `15 bps` per completed rebalance;
- stress: `30 bps` per completed rebalance.

No alternative maturity, factor, filter, lookback, K, holding period or symbol
subset may be inspected in this experiment. Any change is XSEC causal V2 and
requires a new untouched interval.

## Outputs

Total return, CAGR, max drawdown, annualized Sharpe, t-stat, price/funding/cost
attribution, phases, calendar-year and monthly returns, red months, skipped and
failed-close counts. A run passport binds code/input hashes before metrics are
computed. Result and passport are write-once.

## Verdict

- `REJECT`: base CAGR `<=0` or stress total return `<=0`.
- `SHADOW_CANDIDATE_ONLY`: base Sharpe `>=0.50`, stress total `>0`, both
  calendar 2024 and available 2025 returns `>0`, and no phase has negative
  total return.
- otherwise `INCONCLUSIVE`.

Even `SHADOW_CANDIDATE_ONLY` carries zero capital until closed-contract PIT,
independent-engine reproduction and prospective broker-ready shadow complete.
