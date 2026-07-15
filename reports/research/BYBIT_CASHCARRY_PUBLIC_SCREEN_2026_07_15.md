# Bybit cash-carry public screen — 2026-07-15

Status: **PUBLIC READ-ONLY / NO KEYS / NO ORDERS / NO ENTRY AUTHORITY**.

The frozen v1 runner queried only public Bybit spot/perpetual top-of-book,
ticker and completed funding history around `2026-07-15T17:16Z`.  The v1
conservative round-trip contract is `39 bps`: two spot fills at `10 bps`, two
perp fills at `5.5 bps`, and four fills with `2 bps` adverse slippage.  Its
maximum hold is 14 days, or at most 42 eight-hour settlements.

| Symbol | Projected funding / 8h | Adverse entry spot-vs-perp basis | Projected 42-settlement carry | Recent persistence | Economics screen |
|---|---:|---:|---:|---|---|
| XRPUSDT | 0.760 bps | 6.29 bps | 31.92 bps | last 4 completed positive | NO_ENTRY |
| BTCUSDT | 0.1875 bps | 3.47 bps | 7.88 bps | last 7 completed positive, projected rate falling | NO_ENTRY |
| ETHUSDT | 0.2511 bps | 4.79 bps | 10.55 bps | last 5 completed positive | NO_ENTRY |
| SOLUSDT | 0.1368 bps | 6.44 bps | 5.75 bps | last 3 include a negative rate | NO_ENTRY |

Even the XRP lead does not cover the frozen `39 bps` four-fill/slippage
contract over the entire maximum hold at the current projected rate, before
charging adverse entry basis, exit basis drift, funding decay, margin or
operational risk.  This invalidates any immediate `$5–15/month per $1000`
claim under the current conservative execution model.

Decision: keep same-exchange cash-carry high in the research queue because it
is directionally hedged, but do not allocate new capital or open even a paper
cycle solely on three positive rates.  V2 must require conservative expected
settlements to cover all fills, fees, entry basis and a stress margin, then
collect the rejected as well as accepted opportunity set.
