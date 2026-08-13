from strategies import alt_trendline_touch_v1 as att1


def test_att1_entry_card_exposes_richer_geometry_without_changing_signal() -> None:
    card = att1._entry_card_text(
        side="short",
        points=[(8, 110.0), (16, 109.0), (24, 108.0)],
        current_index=30,
        trendline_level=107.25,
        entry=106.80,
        touch_extreme=107.35,
        close=106.80,
        open_=107.10,
        high=107.35,
        low=106.60,
        atr=1.0,
        timestamps=[1_700_000_000_000 + i * 3_600_000 for i in range(31)],
    )

    for field in ("r2=", "pivots=3", "age=6", "entrydist=", "touchdist=", "reject=", "body=", "atrpct="):
        assert field in card
    assert "anchors=1700028800000:110|1700057600000:109|1700086400000:108" in card


def test_att1_short_rsi_max_loads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ATT1_RSI_SHORT_MAX", "70")

    strategy = att1.AltTrendlineTouchV1Strategy()

    assert strategy.cfg.rsi_short_max == 70.0


def test_att1_min_entry_distance_is_default_noop_and_explicit_challenger(monkeypatch) -> None:
    monkeypatch.delenv("ATT1_MIN_ENTRY_DIST_ATR", raising=False)
    champion = att1.AltTrendlineTouchV1Strategy()
    assert champion.cfg.min_entry_dist_atr == 0.0

    monkeypatch.setenv("ATT1_MIN_ENTRY_DIST_ATR", "0.5")
    challenger = att1.AltTrendlineTouchV1Strategy()
    assert challenger.cfg.min_entry_dist_atr == 0.5


def test_att1_geometry_v2_is_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("ATT1_GEOMETRY_V2_ENABLE", raising=False)
    monkeypatch.delenv("ATT1_GEOMETRY_V2_OBSERVE", raising=False)
    champion = att1.AltTrendlineTouchV1Strategy()
    assert champion.cfg.geometry_v2_enable is False
    assert champion.cfg.geometry_v2_observe is False

    monkeypatch.setenv("ATT1_GEOMETRY_V2_ENABLE", "1")
    challenger = att1.AltTrendlineTouchV1Strategy()
    assert challenger.cfg.geometry_v2_enable is True

    monkeypatch.setenv("ATT1_GEOMETRY_V2_ENABLE", "0")
    monkeypatch.setenv("ATT1_GEOMETRY_V2_OBSERVE", "1")
    observer = att1.AltTrendlineTouchV1Strategy()
    assert observer.cfg.geometry_v2_enable is False
    assert observer.cfg.geometry_v2_observe is True


def test_att1_short_rejects_rsi_above_configured_max(monkeypatch) -> None:
    cfg = att1.AltTrendlineTouchV1Config(
        signal_lookback=20,
        pivot_left=1,
        pivot_right=1,
        min_pivots=2,
        max_pivots_used=2,
        max_pivot_age=20,
        min_slope_pct=0.01,
        max_slope_pct=10.0,
        short_max_pos_slope=1.0,
        min_r2=0.0,
        touch_atr=1.0,
        reject_atr=0.0,
        min_body_frac=0.0,
        rsi_short_min=50.0,
        rsi_short_max=70.0,
    )
    strategy = att1.AltTrendlineTouchV1Strategy(cfg)
    highs = [110.0 - i * 0.1 for i in range(20)]
    closes = [value - 0.4 for value in highs]
    opens = [value - 0.2 for value in highs]
    lows = [value - 0.8 for value in highs]
    monkeypatch.setattr(att1, "_find_swing_highs", lambda *_: [(8, highs[8]), (16, highs[16])])

    result = strategy._check_short_trendline(highs, closes, opens, lows, atr=1.0, rsi=75.0)

    assert result is None
    assert strategy._last_no_signal_reason == "short_rsi_too_high"


def test_att1_short_min_entry_distance_blocks_too_close_challenger(monkeypatch) -> None:
    cfg = att1.AltTrendlineTouchV1Config(
        signal_lookback=20,
        pivot_left=1,
        pivot_right=1,
        min_pivots=2,
        max_pivots_used=2,
        max_pivot_age=20,
        min_slope_pct=0.01,
        max_slope_pct=10.0,
        short_max_pos_slope=1.0,
        min_r2=0.0,
        touch_atr=1.0,
        reject_atr=0.0,
        min_body_frac=0.0,
        rsi_short_min=50.0,
        rsi_short_max=70.0,
        min_entry_dist_atr=0.5,
        allow_longs=False,
    )
    strategy = att1.AltTrendlineTouchV1Strategy(cfg)
    rows = [
        [index * 3_600_000, 108.0, 108.3, 107.4, 107.7, 1.0]
        for index in range(20)
    ]

    class Store:
        symbol = "BTCUSDT"

        @staticmethod
        def fetch_klines(*_args):
            return rows

    strategy._last_tf_ts = -1
    monkeypatch.setattr(att1, "_atr_from_rows", lambda *_: 1.0)
    monkeypatch.setattr(att1, "_rsi", lambda *_: 60.0)
    monkeypatch.setattr(strategy, "_check_short_trendline", lambda *_: (108.1, -0.1))

    result = strategy.maybe_signal(Store(), rows[-1][0], 0.0, 0.0, 0.0, 0.0)

    assert result is None
    assert strategy._last_no_signal_reason == "short_entry_too_close_to_line"
