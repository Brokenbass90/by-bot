from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_live_regime_builder_uses_isolated_direction_prefixes():
    source = (ROOT / "scripts" / "build_regime_state.py").read_text(encoding="utf-8")
    assert '"ASB1_ALLOW_' not in source
    assert '"ASLB1_ALLOW_LONGS"' in source
    assert '"ASLB1_ALLOW_SHORTS"' in source
    assert '"BOUNCE1_ALLOW_LONGS"' in source
    assert '"BOUNCE1_ALLOW_SHORTS"' in source


def test_legacy_regime_orchestrator_uses_isolated_direction_prefixes():
    source = (ROOT / "bot" / "regime_orchestrator.py").read_text(encoding="utf-8")
    assert '"ASB1_ALLOW_' not in source
    assert '"ASLB1_ALLOW_LONGS"' in source
    assert '"ASLB1_ALLOW_SHORTS"' in source
    assert '"BOUNCE1_ALLOW_LONGS"' in source
    assert '"BOUNCE1_ALLOW_SHORTS"' in source

