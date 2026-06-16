# Funding Carry Gate

Verdict: **NO-GO**
Net: `$4.22`
Annualized on notional: `1.1%`
Run dir: `backtest_runs/funding_20260616_080919_funding_carry_180d_spot_hedgeable_stress`

## Inputs

- symbols: `SUIUSDT, LINKUSDT, LTCUSDT, NEARUSDT, HYPEUSDT, DOGEUSDT, AVAXUSDT, BNBUSDT`
- notional: `$800.00` total / `$100.00` per symbol
- gross funding: `$10.26`
- fees from funding run: `$2.40`
- extra hedge/spread cost: `$0.64`
- basis P&L: `$-3.00`

## Window Check

- positive windows: `5/7`
- worst window after allocated costs: `$-0.23`
- monthly net after allocated costs: `[0.078554, 1.156238, -0.2314, 0.219136, 1.226267, 1.77243, -0.001778]`

## Failed

- annualized 1.1% >= 4.0% on notional

## Passed

- net $4.22 > $0.0 after fees+hedge+basis
- consistency 0.71 >= 0.6 (5/7 windows)
- worst-window tail 0.0% <= 5.0% (liquidation/basis)
