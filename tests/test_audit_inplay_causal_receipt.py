from scripts.audit_inplay_causal_receipt import audit


def test_current_inplay_receipt_is_shadow_only_not_capital():
    result = audit(
        __import__("pathlib").Path("research_lab/results/path_sim_v4_causal_preholdout_r2/run_passport.json"),
        __import__("pathlib").Path("research_lab/results/path_sim_v4_causal_preholdout_r2/inplay_breakout__ETHUSDT.json"),
    )
    assert result["verdict"] == "CAUSAL_VIABLE_SHADOW_ONLY"
    assert result["positive_folds"] == 3
    assert result["capital_authorized"] is False
