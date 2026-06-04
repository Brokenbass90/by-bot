import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_att1_rounding_reject_records_raw_and_rounded_levels() -> None:
    tree = ast.parse((ROOT / "smart_pump_reversal_bot.py").read_text(encoding="utf-8"))
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "try_att1_entry_async"
    )
    trace_call = next(
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_append_signal_decision"
        and len(node.args) >= 3
        and isinstance(node.args[2], ast.Constant)
        and node.args[2].value == "skip_rounding"
    )

    keys = {keyword.arg for keyword in trace_call.keywords}
    assert {
        "use_runner",
        "entry_raw",
        "tp_raw",
        "sl_raw",
        "tp_rounded",
        "sl_rounded",
    } <= keys
