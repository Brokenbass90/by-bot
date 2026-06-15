"""Tests for the unified on-board-AI toolbox."""

from bot import ai_tools


def test_manifest_lists_read_and_gated_write():
    tools = ai_tools.available_tools()
    names = {t["name"] for t in tools}
    assert {"get_pulse", "get_strategy_catalog", "read_code", "search_code"} <= names
    # the only write channel must be the human-gated proposal path
    writes = [t for t in tools if t["kind"].startswith("write")]
    assert len(writes) == 1
    assert "deepseek_action_executor" in writes[0]["desc"]
    assert "HUMAN" in writes[0]["desc"]


def test_strategy_catalog_accessible():
    cat = ai_tools.get_strategy_catalog()
    assert "families" in cat and "active_keys" in cat


def test_read_code_is_secret_safe():
    # reading .env must be refused through the toolbox too
    out = ai_tools.read_code(".env")
    assert out.startswith("refused")


def test_search_code_finds_signal_api():
    hits = ai_tools.search_code("def maybe_signal", "strategies")
    assert isinstance(hits, list)


def test_list_modules_returns_files():
    mods = ai_tools.list_modules("bot")
    assert any(m.endswith("ai_tools.py") for m in mods)
