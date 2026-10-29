# Gold MT5 demo preflight — 29 October 2026

Status: DEMO_READBACK_AND_NATIVE_CALCULATIONS_PASS. Actual order lifecycle NOT_TESTED.

Owner opened MetaQuotes-Demo explicitly as a test environment. Existing local
signal_copy transport now works: GET /api/status ok=true, MT5 build6259,
server_connected=true, account type=demo, currency=EUR, hedging. Bullwaves remains
owner-reported only; these are not its account conditions or live execution proof.

## Actual checks

- Existing localhost8766 backend and22346 MCP listening. Reused configured local
  authentication; no token values displayed or credentials/settings changed.
- XAUUSD quoted; readback16:45:22UTC bid4016.66/ask4016.96, instantaneous spread0.30.
  Min/step0.01lot, contract100, tick_size0.01. Ten H1 bars returned through existing
  read-only API; bar time semantics/freshness not yet accepted for strategy use.
- tick_value0.1 conflicts with contract and account FX conversion. Existing sibling
  sizing helper chooses the more conservative contract calculation with warning.
  For a hypothetical $1 adverse move per1lot it calculated89.59EUR, not10EUR.
- Runtime MCP tools/list documented trade_order_calc_profit and
  trade_order_calc_margin as mathematical only, without orders/account changes.
  Both BUY/SELL hypothetical0.01lot checks returned profit -0.90EUR for $1 adverse
  movement, and margin35.99EUR at reference4017.38. This agrees with contract sizing
  at the terminal's rounding; it does not validate every symbol/price/size case.
- margin_initial=0 is NOT zero required margin; the native calculator proves a
  nonzero requirement. Fees, swaps and slippage are outside these calculations.

## Boundaries and next gate

No trade_send/check, close, stop modification, symbol addition, Telegram action,
autocopy/allowlist change or application restart. Order calls0, broker writes0.
Monthly/PUMP4 and KITY hold unchanged. No strategy or gold income claim.

The demo environment is available for the existing gold mechanism's engineering
checks. Before an actual demo lifecycle, fix a reproducible test signal/scenario,
volume and stop/exit contract; verify closed-bar times, preflight with native
check, then capture entry/native protection/restart/exit receipts. An arbitrary
market entry is not a strategy test. Actual Bullwaves/news spread, slippage and
point-in-time macro data remain separate research/venue gates.

Receipts: reports/evidence/gold_demo_preflight_20261029/readback.json and
native_calculations.json. They omit login, account balances and credentials.
