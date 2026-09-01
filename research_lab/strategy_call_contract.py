"""Fail-closed invocation contract for the strategy corpus."""

from __future__ import annotations

import inspect
from typing import Callable, Literal


FirstSignalArgument = Literal["store", "symbol"]


class StrategyCallContractError(ValueError):
    """Raised when a strategy's call signature is outside the declared corpus."""


def first_signal_argument(obj: object) -> FirstSignalArgument:
    """Return whether a bound ``maybe_signal`` expects a store or a symbol."""
    fn = getattr(obj, "maybe_signal", None)
    if not callable(fn):
        raise StrategyCallContractError("strategy has no callable maybe_signal")
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError) as exc:
        raise StrategyCallContractError("cannot inspect maybe_signal") from exc
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    ]
    if not positional:
        raise StrategyCallContractError("maybe_signal has no first argument")
    name = positional[0].name
    if name == "store":
        return "store"
    if name == "symbol":
        return "symbol"
    raise StrategyCallContractError(f"unsupported maybe_signal first argument: {name}")


def build_ohlcv_caller(
    obj: object,
    *,
    store: object,
    symbol: str,
) -> Callable[[int, float, float, float, float, float], object]:
    """Bind the declared first argument once and return a bar-level caller."""
    first = first_signal_argument(obj)
    first_value = str(symbol) if first == "symbol" else store
    fn = getattr(obj, "maybe_signal")

    def call(ts_ms: int, o: float, h: float, l: float, c: float, v: float = 0.0):
        return fn(first_value, ts_ms, o, h, l, c, v)

    return call
