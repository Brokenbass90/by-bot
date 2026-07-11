from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _env(path: Path) -> dict[str, str]:
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_approved_baseline_is_fail_safe_without_operator_override():
    values = _env(ROOT / "configs" / "approved_strategy_params.env")
    risk_values = {
        key: float(value)
        for key, value in values.items()
        if key.endswith("_RISK_MULT") and key not in {"ORCH_GLOBAL_RISK_MULT", "ALLOCATOR_GLOBAL_RISK_MULT"}
    }

    assert values["ENABLE_ATT1_TRADING"] == "1"
    assert values["ATT1_ALLOW_LONGS"] == "0"
    assert values["ATT1_ALLOW_SHORTS"] == "1"
    assert values["ATT1_RSI_SHORT_MIN"] == "45"
    assert risk_values["ATT1_RISK_MULT"] == 0.10
    assert all(value == 0.0 for key, value in risk_values.items() if key != "ATT1_RISK_MULT")
    assert values["ENABLE_FLAT_TRADING"] == "0"
    assert values["ENABLE_RANGE_TRADING"] == "0"


def test_approved_att1_geometry_matches_r001_operator_override():
    approved = _env(ROOT / "configs" / "approved_strategy_params.env")
    r001 = _env(ROOT / "configs" / "att1_short_r001_canary_20260702.env")
    active = _env(ROOT / "configs" / "att1_r001_plus_ivb1_r003_shadow_20260705.env")

    for key in (
        "ATT1_RISK_MULT",
        "ATT1_ALLOW_LONGS",
        "ATT1_ALLOW_SHORTS",
        "ATT1_PIVOT_LEFT",
        "ATT1_PIVOT_RIGHT",
        "ATT1_MIN_PIVOTS",
        "ATT1_MAX_PIVOT_AGE",
        "ATT1_MIN_R2",
        "ATT1_TOUCH_ATR",
        "ATT1_RSI_SHORT_MIN",
    ):
        assert float(approved[key]) == float(r001[key]), key
        assert float(active[key]) == float(r001[key]), key


def test_heartbeat_uses_dynamic_att1_contract_helper():
    source = (ROOT / "smart_pump_reversal_bot.py").read_text(encoding="utf-8")

    assert "build_att1_runtime_contract(risk_mult=ATT1_RISK_MULT)" in source
    assert '"att1_effective_params": _att1_contract["params"]' in source
    assert '"att1_effective_params_sha256": _att1_contract["sha256"]' in source
    assert "ATT1_RSI_SHORT_MIN" not in source
