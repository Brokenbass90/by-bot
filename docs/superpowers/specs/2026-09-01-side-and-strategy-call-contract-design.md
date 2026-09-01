# Side and Strategy Call Contract Design

## Purpose

Remove two silent research/live contract splits before any GS1/PUMP4 result is
used:

1. Internal strategy/research code uses `long` / `short`, while exchange
   boundaries use `Buy` / `Sell`.
2. Most corpus strategies expect `maybe_signal(store, ...)`, while four pump
   strategies expect `maybe_signal(symbol, ...)`.

The repair is research/backtest only until its tests and reruns pass. It does
not change live risk, slots, money authority, services, or orders.

## Binding contracts

### Direction vocabulary

- Canonical internal values are exactly `long` and `short`.
- Accepted boundary aliases are case-insensitive `long`, `short`, `buy`, and
  `sell`.
- Unknown, empty, or non-string values fail closed; no `else means short` and
  no absolute-distance fallback is allowed.
- Conversion to the Bybit vocabulary happens explicitly through one helper and
  yields exactly `Buy` or `Sell`.
- `TradeSignal` producers must emit canonical internal values. GS1 is repaired
  at its source rather than relying on a later coercion.

### Strategy call vocabulary

- The invocation contract inspects the first positional parameter of the bound
  `maybe_signal` method.
- A parameter named `symbol` receives the explicit symbol string.
- A parameter named `store` receives the store object.
- Any other first-argument name fails closed with a diagnostic error; it is not
  guessed from arity.
- The four known symbol-first strategies are:
  `pump_fade_simple`, `pump_fade_v2`, `pump_fade_v4r`, and
  `pump_momentum_v1`.
- Existing async and short-form conventions remain supported by the generic
  adapter; this change only makes the first-argument dimension explicit.

## Evidence and invalidation

- Existing GS1 passports and package results are invalid until recomputed after
  both contracts pass.
- The current `research_lab/passport_gs1.json` contains zero cells and is
  retained as pre-fix evidence, not overwritten without a receipt.
- PUMP4 historical values are not promoted by this repair. A same-input
  before/after signal-count comparison is diagnostic only, and the current
  multiple-testing verdict remains binding.
- The rerun receipt records source SHA, config/data identities, commands,
  pre-fix artifact hashes, resulting artifact hashes, and any blockers.

## Safety boundaries

- No broker/private API calls.
- No live configuration, risk, orders, positions, or money authority changes.
- No sealed/reserved-OOS reads or reruns.
- Tests must demonstrate the pre-fix failure before production code changes.

