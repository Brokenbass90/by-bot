from pathlib import Path

from strategies.inplay_retest_v3 import InplayRetestV3Strategy


ROOT = Path(__file__).resolve().parents[1]
LADDER = ROOT / "scripts" / "retest3_stop_ladder.sh"


def test_ladder_uses_the_strategy_stop_environment_contract():
    source = LADDER.read_text(encoding="utf-8")

    assert "IRV3_STOP_BUFFER_ATR" in source
    assert "export RETEST3_STOP_MULT" not in source
    assert "RETEST3_PREFLIGHT_ONLY" in source
    assert "RETEST3_TAG_SUFFIX" in source
    assert "PYTHON_BIN" in source


def test_stop_environment_values_resolve_to_distinct_configs(monkeypatch):
    expected = [0.35, 0.525, 0.70, 0.875]
    actual = []

    for value in expected:
        monkeypatch.setenv("IRV3_STOP_BUFFER_ATR", str(value))
        actual.append(InplayRetestV3Strategy().cfg.stop_buffer_atr)

    assert actual == expected
    assert len(set(actual)) == len(expected)
