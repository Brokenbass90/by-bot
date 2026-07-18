# Bybit account fee receipt — 2026-07-18

Evidence class: **read-only account receipt**. No order, transfer, withdrawal, key
change or capital allocation was performed.

## Verified account tier

The authenticated Bybit V5 `GET /v5/account/fee-rate` endpoint was queried for
the existing `main` account. Secret material, account identifiers and request
signatures are intentionally excluded from this report.

| Market / symbol | maker | taker | maker (bps) | taker (bps) |
|---|---:|---:|---:|---:|
| spot `BTCUSDT` | `0.001` | `0.001` | 10.0 | 10.0 |
| linear `BTCUSDT` | `0.0002` | `0.00055` | 2.0 | 5.5 |

Observed at: `2026-07-18` UTC. The API is authoritative for the current account
tier, but the tier can change; promotion preflight must refresh this receipt.

## Cash-carry consequence

The frozen conservative path assumes taker execution on all four fills:

`spot buy 10 + perp sell 5.5 + spot sell 10 + perp buy 5.5 = 31 bps`.

That exactly matches the current station's `four_fill_fee_bps=31`. Even a
perfect maker fill on both perpetual legs would reduce the round-trip fee by
only `7 bps`; it would not bridge the current station's roughly `54–61 bps`
required-carry threshold while observed conservative funding remains far lower.

Therefore:

- the current public station's repeated `NO_ENTRY` is not caused by an
  accidentally inflated fee tier;
- expected income remains **unknown**, not `$5–15/month per $1000`;
- no cash-carry capital is authorized until stressed paper economics and the
  two-leg recovery lifecycle pass.

Official endpoint contract:
`https://bybit-exchange.github.io/docs/v5/account/fee-rate`.
