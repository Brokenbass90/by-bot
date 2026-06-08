from pathlib import Path


def test_main_applies_static_global_risk_before_optional_overlays() -> None:
    src = Path("smart_pump_reversal_bot.py").read_text(encoding="utf-8")
    main_body = src.split("def main():", 1)[1].split('if __name__ == "__main__":', 1)[0]

    recompute_pos = main_body.index("_recompute_effective_risk_pct()")
    regime_pos = main_body.index("_apply_regime_overlay(force=True, notify=False)")
    allocator_pos = main_body.index("_apply_portfolio_allocator_overlay(force=True, notify=False)")

    assert recompute_pos < regime_pos < allocator_pos


def test_heartbeat_exposes_effective_risk_controls() -> None:
    src = Path("smart_pump_reversal_bot.py").read_text(encoding="utf-8")

    for key in (
        '"risk_per_trade_pct"',
        '"base_risk_per_trade_pct"',
        '"orch_global_risk_mult"',
        '"allocator_global_risk_mult"',
        '"max_open_portfolio_risk_pct"',
        '"max_positions"',
    ):
        assert key in src
