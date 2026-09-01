from strategies.signals import TradeSignal
from strategies.pump_fade_smart_v1 import PumpFadeSmartV1Strategy
from strategies.grid_smart_v1 import GridSmartV1Strategy


class _GS1Store:
    symbol = "BTCUSDT"

    def __init__(self) -> None:
        self.rows = [
            [1_700_000_000_000 + i * 3_600_000, 100.0, 101.0, 99.0, 100.0, 10.0]
            for i in range(60)
        ]

    def fetch_klines(self, symbol, timeframe, limit):
        assert symbol == self.symbol
        return self.rows[-limit:]


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


def _gs1_signal(*, side: str) -> TradeSignal:
    strategy = GridSmartV1Strategy()
    strategy.cfg.regime_mode = "force_on"
    strategy.cfg.grid_anchor_mode = "mid_range"
    strategy.cfg.level_atr_mult = 0.5
    strategy.cfg.sl_buffer_atr = 0.0
    strategy.cfg.tp_buffer_atr = 0.0
    strategy.cfg.max_slope_pct = 1.0
    strategy.cfg.er_max = 1.0
    strategy.cfg.cooldown_bars_15m = 0
    strategy.cfg.allow_longs = side == "long"
    strategy.cfg.allow_shorts = side == "short"
    price = 99.0 if side == "long" else 101.0
    signal = strategy.maybe_signal(
        _GS1Store(),
        1_800_000_000_000,
        price,
        price,
        price,
        price,
        10.0,
    )
    assert signal is not None
    return signal


def test_gs1_emits_canonical_valid_long_signal():
    signal = _gs1_signal(side="long")
    assert signal.side == "long"
    assert signal.validate()


def test_gs1_emits_canonical_valid_short_signal():
    signal = _gs1_signal(side="short")
    assert signal.side == "short"
    assert signal.validate()


def test_pfs1_detects_pump_before_rejection_bar():
    strategy = PumpFadeSmartV1Strategy()
    strategy.cfg.pump_lookback_bars = 6
    strategy.cfg.pump_min_pct = 3.0
    strategy.cfg.vol_z_min = 1.0

    closes = [100.0] * 70 + [100.0, 100.5, 101.0, 102.0, 103.0, 104.0, 100.4]
    # highs track the pump's intrabar extremes; _detect_pump measures the run
    # from start close to the max high of the lookback window (excluding the
    # current rejection bar). See pump_fade_smart_v1._detect_pump signature
    # (closes, highs, volumes) added in the 2026-06 strategy audit repair.
    highs = [100.0] * 70 + [100.2, 100.7, 101.2, 102.2, 103.2, 104.2, 104.2]
    volumes = [10.0] * 70 + [10.0, 10.0, 10.0, 80.0, 80.0, 80.0, 80.0]

    detected, pump_pct, _, _ = strategy._detect_pump(closes, highs, volumes)
    assert detected
    assert pump_pct >= 3.0
