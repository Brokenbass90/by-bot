import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _att1_function() -> ast.AsyncFunctionDef:
    tree = ast.parse((ROOT / "smart_pump_reversal_bot.py").read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "try_att1_entry_async"
    )


def _first_line(fn: ast.AsyncFunctionDef, predicate) -> int:
    return min(node.lineno for node in ast.walk(fn) if predicate(node))


def test_att1_defines_signal_reason_before_market_submit() -> None:
    fn = _att1_function()
    reason_line = _first_line(
        fn,
        lambda node: (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Store)
            and node.id == "signal_reason"
        ),
    )
    submit_line = _first_line(
        fn,
        lambda node: (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_submit_entry_order_guarded"
        ),
    )

    assert reason_line < submit_line


def test_att1_adopts_acknowledged_order_before_optional_hooks() -> None:
    fn = _att1_function()
    adoption_line = _first_line(
        fn,
        lambda node: (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "TRADES"
                for target in node.targets
            )
        ),
    )
    geometry_line = _first_line(
        fn,
        lambda node: (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "build_position_geometry"
        ),
    )
    bus_line = _first_line(
        fn,
        lambda node: (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "record_entry"
        ),
    )

    assert adoption_line < geometry_line
    assert adoption_line < bus_line
