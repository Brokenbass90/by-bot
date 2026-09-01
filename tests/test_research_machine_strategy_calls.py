from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from research_lab.research_machine import (
    SignalCallDiagnostics,
    Store,
    build_research_signal_caller,
)


ROOT = Path(__file__).resolve().parents[1]


def test_research_machine_direct_script_entrypoint_loads_contract() -> None:
    result = subprocess.run(
        [sys.executable, "research_lab/research_machine.py", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--strategy" in result.stdout


def test_research_machine_passes_explicit_symbol_to_symbol_first_strategy() -> None:
    seen = []

    class SymbolFirst:
        def maybe_signal(self, symbol, ts_ms, o, h, l, c, v=0.0):
            seen.append(symbol)
            return "signal"

    store = Store("ETHUSDT")
    caller = build_research_signal_caller(SymbolFirst(), store)
    bar = [1, 2.0, 3.0, 1.0, 2.5, 4.0]

    assert caller(bar) == "signal"
    assert seen == ["ETHUSDT"]


def test_research_machine_preserves_store_for_store_first_strategy() -> None:
    seen = []

    class StoreFirst:
        def maybe_signal(self, store, ts_ms, o, h, l, c, v=0.0):
            seen.append(store)
            return "signal"

    store = Store("SOLUSDT")
    caller = build_research_signal_caller(StoreFirst(), store)
    bar = [1, 2.0, 3.0, 1.0, 2.5, 4.0]

    assert caller(bar) == "signal"
    assert seen == [store]


def test_signal_call_exceptions_are_counted_and_invalidate_the_run() -> None:
    diagnostics = SignalCallDiagnostics(sample_limit=2)

    def broken(_bar):
        raise RuntimeError("fixture failure")

    assert diagnostics.invoke(broken, [123, 1, 2, 0, 1, 9], symbol="BTCUSDT") is None

    receipt = diagnostics.as_dict()
    assert receipt["calls"] == 1
    assert receipt["errors"] == 1
    assert receipt["complete"] is False
    assert receipt["error_types"] == {"RuntimeError": 1}
    assert receipt["samples"] == [
        {
            "symbol": "BTCUSDT",
            "ts_ms": 123,
            "error_type": "RuntimeError",
            "message": "fixture failure",
        }
    ]
