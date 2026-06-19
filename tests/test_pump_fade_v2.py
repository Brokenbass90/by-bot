import json
from pathlib import Path

from strategies.pump_fade_v2 import PumpFadeV2Config, PumpFadeV2Strategy


def test_cooldown_uses_market_time_not_call_count():
    strategy = PumpFadeV2Strategy(PumpFadeV2Config(cooldown_bars=2, pump_window_bars=1, confirm_bars=1))
    base_ts = 1_700_000_000_000
    strategy._cooldown_until_ts_ms = base_ts + 600_000

    assert strategy.maybe_signal("BTCUSDT", base_ts, 100, 101, 99, 100, 10) is None
    assert strategy.last_no_signal_reason == "cooldown"
    assert len(strategy._bars) == 0

    # Repeated calls on the same bar must not consume cooldown.
    assert strategy.maybe_signal("BTCUSDT", base_ts, 100, 101, 99, 100, 10) is None
    assert strategy._cooldown_until_ts_ms == base_ts + 600_000

    assert strategy.maybe_signal("BTCUSDT", base_ts + 600_000, 100, 101, 99, 100, 10) is None
    assert len(strategy._bars) == 1


def test_research_spec_uses_real_strategy_parameter_names():
    path = Path(__file__).resolve().parents[1] / "configs" / "autoresearch" / "pump_fade_v5_bear_window_v1.json"
    spec = json.loads(path.read_text(encoding="utf-8"))

    assert set(spec["grid"]) == {"PF2_MIN_PUMP_PCT", "PF2_PUMP_WINDOW_BARS", "PF2_RSI_OB"}
    assert spec["_combo_count"] == 12
    assert "--entry-on-next-open" in spec["command"]
