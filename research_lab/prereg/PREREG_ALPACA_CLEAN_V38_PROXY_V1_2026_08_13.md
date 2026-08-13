# PREREG: Alpaca clean-subset v38 structural proxy v1

Frozen 2026-08-13. Research only; SAFE_HOLD, broker state and capital authority
must not change.

## Question

Is the frozen v38 successor selection structurally positive on the 962-symbol
integrity-clean Alpaca/Massive daily subset under the current deployable
protection proxy at base and stress costs?

## Fixed contract

- Input: adjusted daily archive `alpaca_pit_daily_v1`, excluding exactly the
  quarantined symbols in its validation receipt.
- Calendar: observed AAPL sessions. This is not an authoritative XNYS ledger.
- Monthly completed close to next observed session open.
- Frozen `select_v38_successor`, top 4, top-18 health universe, existing sector
  map and frozen cluster list. Unknown-sector behavior is preserved and audited.
- One cash-aware portfolio, 70% target gross exposure, retained positions are
  not fictitiously rotated.
- Current deployable fractional protection through the conservative daily
  proxy. Its 15-minute live sampling cannot be reproduced from daily bars.
- Base cost 5 bps per side; stress cost 10 bps per side.
- One contract and two predeclared cost scenarios; no parameter search.

## Interpretation

The output may answer the sign of this structural proxy only. It can never
authorize promotion because full-market PIT membership, complete sector data,
authoritative XNYS sessions, delisting cashflows and intraday protection parity
are unresolved. Positive base and stress is `DIAGNOSTIC_POSITIVE_BOTH`; any
non-positive scenario is `DIAGNOSTIC_NOT_POSITIVE_BOTH`.
