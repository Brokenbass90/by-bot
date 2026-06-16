# Funding Carry Gate

Verdict: **NO-GO**
Net: `$7.22`
Annualized on notional: `1.8%`
Run dir: `backtest_runs/funding_20260616_080919_funding_carry_180d_spot_hedgeable_stress`

## Inputs

- symbols: `SUIUSDT, LINKUSDT, LTCUSDT, NEARUSDT, HYPEUSDT, DOGEUSDT, AVAXUSDT, BNBUSDT`
- notional: `$800.00` total / `$100.00` per symbol
- gross funding: `$10.26`
- fees from funding run: `$2.40`
- extra hedge/spread cost: `$0.64`
- basis P&L: `$0.00`

## Window Check

- positive windows: `7/7`
- worst window after allocated costs: `$0.20`
- monthly net after allocated costs: `[0.507125, 1.584809, 0.197171, 0.647707, 1.654838, 2.201001, 0.426793]`

## Failed

- annualized 1.8% >= 4.0% on notional

## Passed

- net $7.22 > $0.0 after fees+hedge+basis
- consistency 1.00 >= 0.6 (7/7 windows)
- worst-window tail 0.0% <= 5.0% (liquidation/basis)
