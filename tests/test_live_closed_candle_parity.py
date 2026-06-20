from __future__ import annotations

import ast
from pathlib import Path

from strategies.live_kline_utils import fetch_closed_klines


ROOT = Path(__file__).resolve().parents[1]


def _class_method_calls(class_name: str, method_name: str) -> set[str]:
    tree = ast.parse((ROOT / "smart_pump_reversal_bot.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                    return {
                        call.func.id
                        for call in ast.walk(child)
                        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                    }
    raise AssertionError(f"{class_name}.{method_name} not found")


def _function_names(function_name: str) -> set[str]:
    tree = ast.parse((ROOT / "smart_pump_reversal_bot.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
    raise AssertionError(f"{function_name} not found")


def test_fetch_closed_klines_requests_replacement_for_open_bar(monkeypatch):
    monkeypatch.setattr("strategies.live_kline_utils.time.time", lambda: 1_800.0)
    rows = [
        [1_200_000, "1", "2", "0.5", "1.5", "100"],
        [1_500_000, "1", "2", "0.5", "1.5", "100"],
        [1_800_000, "1", "2", "0.5", "1.5", "100"],
    ]
    calls = []

    def fake_fetch(symbol, interval, limit):
        calls.append((symbol, interval, limit))
        return rows

    assert fetch_closed_klines(fake_fetch, "BTCUSDT", "5", 2) == rows[:2]
    assert calls == [("BTCUSDT", "5", 3)]


def test_live_range_ivb1_and_elder_use_closed_kline_adapter():
    assert "_fetch_closed_klines" in _function_names("fetch_klines_for_range")
    assert "_fetch_closed_klines" in _class_method_calls("_IVB1Store", "fetch_klines")
    assert "_fetch_closed_klines" in _class_method_calls("_ElderStore", "fetch_klines")
