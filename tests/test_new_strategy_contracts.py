from strategies.signals import TradeSignal
from strategies.pump_fade_smart_v1 import PumpFadeSmartV1Strategy


def test_new_strategy_signal_contracts_validate():
    pfs1 = TradeSignal(
        strategy="pump_fade_smart_v1",
        symbol="BTCUSDT",
        side="short",
        entry=100.0,
        sl=102.0,
        tp=97.0,
    )
    gs1 = TradeSignal(
        strategy="grid_smart_v1",
        symbol="BTCUSDT",
        side="long",
        entry=100.0,
        sl=98.0,
        tp=102.0,
    )
    assert pfs1.validate()
    assert gs1.validate()


def test_pfs1_detects_pump_before_rejection_bar():
    strategy = PumpFadeSmartV1Strategy()
    strategy.cfg.pump_lookback_bars = 6
    strategy.cfg.pump_min_pct = 3.0
    strategy.cfg.vol_z_min = 1.0

    closes = [100.0] * 70 + [100.0, 100.5, 101.0, 102.0, 103.0, 104.0, 100.4]
    volumes = [10.0] * 70 + [10.0, 10.0, 10.0, 80.0, 80.0, 80.0, 80.0]

    detected, pump_pct, _, _ = strategy._detect_pump(closes, volumes)
    assert detected
    assert pump_pct >= 3.0
