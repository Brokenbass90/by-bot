# Replayable Bybit tape — start receipt 2026-07-14

Это data-collection receipt, не результат стратегии и не разрешение на торговлю.

- Code: commit `4db0f4d`, pushed to `origin/codex/dynamic-symbol-filters`.
- Full regression at start: `1283 passed`.
- Public-only contract: Bybit V5 public linear WebSocket, no API keys, auth, REST trading client or orders.
- Local process `l2_ondo_v1_20260714`: `ONDOUSDT`, depth-50 orderbook + publicTrade, root `runtime/tape/bybit_l2_ondo_v1`, cap `20 GiB`, minimum free `80 GiB`, retention `stop`, completed-day zstd enabled.
- Local process `trades_micro_v1_20260714`: publicTrade for `ONDOUSDT,WIFUSDT,SUIUSDT,DOGEUSDT,1000PEPEUSDT,FILUSDT`, root `runtime/tape/bybit_trades_micro_v1`, cap `8 GiB`, minimum free `80 GiB`, retention `stop`, completed-day zstd enabled.
- First ONDO read-only replay: one snapshot, `354` deltas, `18` trades, `0` gaps; book and trade streams valid.
- Runtime truth lives in each root's `heartbeat.json` and `manifest.json`; process existence must also be checked with `screen -ls`.

Next gate: one full UTC day, then validate both streams, record bytes/day, zstd ratio, gaps, duplicate trades and connected coverage. No strategy outcome may be inferred from collector health.
