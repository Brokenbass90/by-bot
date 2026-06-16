# Funding Carry Gate

Verdict: **NO-GO**
Net: `$0.10`
Annualized on notional: `1.2%`
Run dir: `backtest_runs/funding_20260616_080859_funding_carry_30d_spot_hedgeable_stress`

## Inputs

- symbols: `SUIUSDT`
- notional: `$100.00` total / `$100.00` per symbol
- gross funding: `$0.48`
- fees from funding run: `$0.30`
- extra hedge/spread cost: `$0.08`
- basis P&L: `$0.00`

## Window Check

- positive windows: `1/2`
- worst window after allocated costs: `$-0.03`
- monthly net after allocated costs: `[0.127385, -0.028194]`

## Failed

- annualized 1.2% >= 4.0% on notional
- consistency 0.50 >= 0.6 (1/2 windows)

## Passed

- net $0.10 > $0.0 after fees+hedge+basis
- worst-window tail 0.0% <= 5.0% (liquidation/basis)
