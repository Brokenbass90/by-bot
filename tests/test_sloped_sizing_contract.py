from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _sloped_entry_function() -> ast.AsyncFunctionDef:
    tree = ast.parse((ROOT / "smart_pump_reversal_bot.py").read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "try_sloped_entry_async"
    )


def test_sloped_sizing_contract_uses_sloped_risk_multiplier() -> None:
    fn = _sloped_entry_function()
    contract = next(
        node.value
        for node in ast.walk(fn)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Dict)
        and any(
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "tr"
            and target.attr == "sizing_contract"
            for target in node.targets
        )
    )
    values_by_key = {
        key.value: value
        for key, value in zip(contract.keys, contract.values)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    risk_value = values_by_key["strategy_risk_multiplier"]

    assert isinstance(risk_value, ast.Call)
    assert isinstance(risk_value.func, ast.Name) and risk_value.func.id == "float"
    assert len(risk_value.args) == 1
    assert isinstance(risk_value.args[0], ast.Name)
    assert risk_value.args[0].id == "SLOPED_RISK_MULT"

    loaded_names = {
        node.id
        for node in ast.walk(fn)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    assert "effective_att1_risk_mult" not in loaded_names
