import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_ivb1_shadow_candidate_is_enabled_with_zero_risk() -> None:
    values = _env_values(ROOT / "configs" / "ivb1_r010_telemetry_shadow.env")

    assert values["ENABLE_IVB1_TRADING"] == "1"
    assert float(values["IVB1_RISK_MULT"]) == 0.0
    assert values["IVB1_ALLOW_MINQTY_FALLBACK"] == "0"


def test_approved_overlay_keeps_ivb1_visible_but_zero_risk() -> None:
    values = _env_values(ROOT / "configs" / "approved_strategy_params.env")
    risk_mult = float(values["IVB1_RISK_MULT"])

    assert values["ENABLE_IVB1_TRADING"] == "1"
    assert risk_mult == 0.0


def test_ivb1_shadow_branch_returns_before_order_submission() -> None:
    tree = ast.parse((ROOT / "smart_pump_reversal_bot.py").read_text(encoding="utf-8"))
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "try_ivb1_entry_async"
    )
    shadow_branch = next(
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "shadow_mode"
    )
    submit_call = next(
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_submit_entry_order_guarded"
    )

    assert shadow_branch.lineno < submit_call.lineno
    assert any(isinstance(node, ast.Return) for node in ast.walk(shadow_branch))
