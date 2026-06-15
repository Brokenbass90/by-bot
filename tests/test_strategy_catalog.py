"""Tests for the AI-facing strategy catalogue."""

from bot.strategy_catalog import build_strategy_catalog, strategy_catalog_prompt_lines


def test_enabled_and_risk_parsed_from_env():
    env = {"ENABLE_ATT1_TRADING": "1", "ATT1_RISK_MULT": "1.0",
           "ENABLE_FLAT_TRADING": "1", "FLAT_RISK_MULT": "0.35",
           "ENABLE_IVB1_TRADING": "1", "IVB1_RISK_MULT": "0.0"}
    cat = build_strategy_catalog(env)
    fams = {f["key"]: f for f in cat["families"]}
    assert fams["att1"]["enabled"] is True
    assert fams["att1"]["risk_mult"] == 1.0
    assert fams["flat"]["risk_mult"] == 0.35
    # IVB1 enabled with zero risk => shadow (telemetry only), not active
    assert fams["ivb1"]["shadow"] is True
    assert "ivb1" not in cat["active_keys"]
    assert "att1" in cat["active_keys"]


def test_runner_model_documents_stop_only_on_exchange():
    cat = build_strategy_catalog({})
    fams = {f["key"]: f for f in cat["families"]}
    # All current live families are runner ladders => only the stop sits on the
    # exchange. This is the fact the AI needs to answer the owner's question.
    assert fams["att1"]["exec_model"] == "runner_ladder"
    assert "только стоп" in fams["att1"]["tpsl_model"]
    assert "runner_ladder" in cat["note"]


def test_disabled_by_default_when_env_empty():
    cat = build_strategy_catalog({})
    assert cat["active_count"] == 0
    assert all(f["enabled"] is False for f in cat["families"])


def test_prompt_lines_are_strings_and_mention_tpsl():
    lines = strategy_catalog_prompt_lines({"ENABLE_MIDTERM_TRADING": "1",
                                           "MIDTERM_RISK_MULT": "1.0"})
    assert all(isinstance(x, str) for x in lines)
    blob = "".join(lines)
    assert "STRATEGY CATALOG" in blob
    assert "MTPB" in blob and "midterm" in blob.lower()
