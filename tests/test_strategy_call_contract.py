from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_lab.strategy_adapter import detect_convention, make_caller
from research_lab.strategy_call_contract import (
    StrategyCallContractError,
    build_ohlcv_caller,
    first_signal_argument,
)
from strategies.grid_smart_v1 import GridSmartV1Strategy
from strategies.pump_fade_simple import PumpFadeSimpleStrategy
from strategies.pump_fade_v2 import PumpFadeV2Strategy
from strategies.pump_fade_v4r import PumpFadeV4RStrategy
from strategies.pump_momentum_v1 import PumpMomentumV1Strategy


ROOT = Path(__file__).resolve().parents[1]


def test_strategy_adapter_direct_script_entrypoint_loads_contract() -> None:
    result = subprocess.run(
        [sys.executable, "research_lab/strategy_adapter.py", "grid_smart_v1", "BTCUSDT"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "ModuleNotFoundError" not in result.stderr


@pytest.mark.parametrize(
    "strategy",
    [
        PumpFadeSimpleStrategy(),
        PumpFadeV2Strategy(),
        PumpFadeV4RStrategy(),
        PumpMomentumV1Strategy(),
    ],
)
def test_known_pump_family_is_explicitly_symbol_first(strategy) -> None:
    assert first_signal_argument(strategy) == "symbol"
    convention, _ = detect_convention(strategy)
    assert convention == "symbol_ohlcv"


def test_store_first_strategy_remains_store_first() -> None:
    strategy = GridSmartV1Strategy()
    assert first_signal_argument(strategy) == "store"
    convention, _ = detect_convention(strategy)
    assert convention == "ohlcv"


def test_unknown_first_parameter_fails_closed_instead_of_guessing() -> None:
    class Ambiguous:
        def maybe_signal(self, context, ts_ms, o, h, l, c, v=0.0):
            return None

    with pytest.raises(StrategyCallContractError, match="first argument"):
        first_signal_argument(Ambiguous())


def test_built_and_generic_callers_pass_symbol_to_symbol_first_strategy() -> None:
    seen = []

    class SymbolFirst:
        def maybe_signal(self, symbol, ts_ms, o, h, l, c, v=0.0):
            seen.append(symbol)
            return "signal"

    obj = SymbolFirst()
    store = object()
    direct = build_ohlcv_caller(obj, store=store, symbol="BTCUSDT")
    assert direct(1, 2.0, 3.0, 1.0, 2.5, 4.0) == "signal"

    candles = [SimpleNamespace(ts=1, o=2.0, h=3.0, l=1.0, c=2.5, v=4.0)]
    generic = make_caller("symbol_ohlcv", obj, "BTCUSDT")
    assert generic(store, candles, 0) == "signal"
    assert seen == ["BTCUSDT", "BTCUSDT"]


def test_built_caller_preserves_store_identity_for_store_first_strategy() -> None:
    seen = []

    class StoreFirst:
        def maybe_signal(self, store, ts_ms, o, h, l, c, v=0.0):
            seen.append(store)
            return "signal"

    obj = StoreFirst()
    store = object()
    caller = build_ohlcv_caller(obj, store=store, symbol="BTCUSDT")
    assert caller(1, 2.0, 3.0, 1.0, 2.5, 4.0) == "signal"
    assert seen == [store]
