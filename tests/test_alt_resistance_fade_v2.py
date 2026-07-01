from pathlib import Path

from strategies.alt_resistance_fade_v2 import AltResistanceFadeV2Config, AltResistanceFadeV2Strategy


def _row(i, o, h, l, c, v=100):
    return [str(i * 3_600_000), str(o), str(h), str(l), str(c), str(v)]


class _Store:
    symbol = "TESTUSDT"

    def __init__(self, signal_rows, regime_rows=None, daily_rows=None, funding=None):
        self.signal_rows = signal_rows
        self.regime_rows = regime_rows or signal_rows
        self.daily_rows = daily_rows or signal_rows
        self.funding = funding

    def fetch_klines(self, symbol, interval, limit):
        assert symbol == self.symbol
        if str(interval) == "60":
            return self.signal_rows[-limit:]
        if str(interval) == "240":
            return self.regime_rows[-limit:]
        if str(interval) == "1440":
            return self.daily_rows[-limit:]
        raise ValueError(interval)

    def fetch_funding_rate(self, symbol):
        assert symbol == self.symbol
        return self.funding


def _cfg(**kw):
    base = dict(
        regime_lookback=24,
        regime_ema_fast=5,
        regime_ema_slow=10,
        regime_min_score=0.05,
        signal_lookback=28,
        signal_ema_period=5,
        signal_atr_period=5,
        rsi_period=5,
        pivot_left=1,
        pivot_right=1,
        min_touches=3,
        level_tol_atr=0.30,
        min_level_score=0.20,
        min_range_pct=1.0,
        reject_below_res_atr=0.03,
        reject_require_lower_close=False,
        min_upper_wick_frac=0.20,
        min_body_frac=0.05,
        min_rsi=0.0,
        max_close_vs_ema_pct=100.0,
        sl_atr_mult=0.30,
        min_rr=0.20,
        min_stop_pct=0.0001,
        max_stop_pct=0.20,
        cooldown_bars_5m=0,
    )
    base.update(kw)
    return AltResistanceFadeV2Config(**base)


def _structured_resistance_rows():
    rows = []
    prev = 100.0
    pivots = [
        100.0, 105.0, 98.0, 101.0,
        105.2, 97.5, 100.5, 105.1,
        98.5, 101.0, 104.8, 97.8,
    ]
    i = 0
    for target in pivots:
        rows.append(_row(i, prev, max(prev, target) + 0.2, min(prev, target) - 0.2, target, 1200 if target > 104 else 400))
        prev = target
        i += 1
    while len(rows) < 32:
        target = 100.0 + (len(rows) % 4) * 0.3
        rows.append(_row(i, prev, max(prev, target) + 0.2, min(prev, target) - 0.2, target, 300))
        prev = target
        i += 1
    reject = _row(i, 104.7, 105.35, 102.8, 103.8, 1500)
    return rows + [reject]


def test_structured_resistance_cluster_is_faded_short():
    rows = _structured_resistance_rows()
    s = AltResistanceFadeV2Strategy(_cfg())
    s._last_tf_ts = int(float(rows[-2][0]))

    sig = s.maybe_signal(_Store(rows), int(float(rows[-1][0])) + 3_600_000, 104.7, 105.35, 102.8, 103.8, 1500)

    assert sig is not None, s.last_no_signal_reason
    assert sig.strategy == "alt_resistance_fade_v2"
    assert sig.side == "short"
    assert sig.tp < sig.entry < sig.sl
    assert "structured_resistance_fade" in sig.reason


def test_no_signal_without_repeated_resistance_cluster():
    rows = _structured_resistance_rows()
    for r in rows[:-1]:
        if float(r[2]) > 104.5:
            r[2] = "103.0"
            r[4] = "102.5"
    s = AltResistanceFadeV2Strategy(_cfg())
    s._last_tf_ts = int(float(rows[-2][0]))

    sig = s.maybe_signal(_Store(rows), int(float(rows[-1][0])) + 3_600_000, 104.7, 105.35, 102.8, 103.8, 1500)

    assert sig is None
    assert s.last_no_signal_reason == "level_not_found"


def test_no_signal_without_bearish_rejection():
    rows = _structured_resistance_rows()
    rows[-1] = _row(200, 104.7, 105.35, 104.6, 105.1, 1500)
    s = AltResistanceFadeV2Strategy(_cfg())
    s._last_tf_ts = int(float(rows[-2][0]))

    sig = s.maybe_signal(_Store(rows), int(float(rows[-1][0])) + 3_600_000, 104.7, 105.35, 104.6, 105.1, 1500)

    assert sig is None
    assert s.last_no_signal_reason == "no_rejection"


def test_level_entry_flag_builds_limit_signal_without_changing_default_path():
    rows = _structured_resistance_rows()
    s = AltResistanceFadeV2Strategy(_cfg(
        use_level_entry=True,
        level_entry_max_chase_atr=10.0,
        level_entry_stop_buffer_atr=0.20,
        level_entry_tp_rr=2.0,
    ))
    s._last_tf_ts = int(float(rows[-2][0]))

    sig = s.maybe_signal(_Store(rows), int(float(rows[-1][0])) + 3_600_000, 104.7, 105.35, 102.8, 103.8, 1500)

    assert sig is not None, s.last_no_signal_reason
    assert sig.side == "short"
    assert getattr(sig, "entry_order_type", None) == "limit"
    assert getattr(sig, "limit_validity_bars", 0) > 0
    assert sig.tp < sig.entry < sig.sl
    assert "level_entry" in sig.reason


def test_run_portfolio_supports_alt_resistance_fade_v2():
    source = (Path(__file__).resolve().parents[1] / "backtest" / "run_portfolio.py").read_text(encoding="utf-8")

    assert 'AltResistanceFadeV2Strategy = _import_strategy_class("alt_resistance_fade_v2", "AltResistanceFadeV2Strategy")' in source
    assert '"alt_resistance_fade_v2"' in source
    assert "alt_resistance_fade_v2[sym].maybe_signal" in source
