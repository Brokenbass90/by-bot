import math

from scripts.validate_pair_arb import simulate_pair
from strategies.alt_inplay_breakdown_v2 import AltInplayBreakdownV2Config, AltInplayBreakdownV2Strategy
from strategies.pair_stat_arb_v1 import PairConfig
from strategies.pump_fade_smart_v1 import PumpFadeSmartV1Strategy


class _BreakdownStore:
    symbol = "TESTUSDT"

    def __init__(self):
        self.rows_1h = []
        price = 104.0
        for i in range(18):
            self.rows_1h.append([str(i), str(price), str(price + 0.8), str(price - 0.8), str(price), "100"])
            price -= 0.05
        # Prior support window: 100.0. Latest completed 1h closes below it.
        self.rows_1h.extend([
            ["18", "101.0", "101.3", "100.0", "100.8", "100"],
            ["19", "100.8", "101.0", "100.0", "100.5", "100"],
            ["20", "100.4", "100.7", "100.0", "100.2", "100"],
            ["21", "100.1", "100.2", "98.7", "98.9", "160"],
        ])
        self.rows_5m = [[str(i), "99.2", "99.3", "99.0", "99.1", "100"] for i in range(19)]
        self.rows_5m.append(["20", "99.2", "99.3", "98.7", "98.8", "160"])

    def fetch_klines(self, symbol, interval, limit):
        rows = self.rows_1h if interval == "60" else self.rows_5m
        return rows[-limit:]


def test_breakdown2_support_excludes_break_bar_and_requires_close():
    cfg = AltInplayBreakdownV2Config(
        lookback_h=3,
        min_break_atr=0.1,
        max_dist_atr=5.0,
        sl_atr=1.0,
        rsi_max=100.0,
        vol_mult=0.0,
        require_1h_close=True,
        cooldown_bars_5m=0,
    )
    sig = AltInplayBreakdownV2Strategy(cfg).maybe_signal(_BreakdownStore(), 22_000, 99.2, 99.3, 98.7, 98.8, 160)
    assert sig is not None
    assert sig.strategy == "alt_inplay_breakdown_v2"
    assert sig.side == "short"
    assert sig.sl > sig.entry > sig.tp


def test_pfs1_detects_high_based_pump_before_rejection():
    s = PumpFadeSmartV1Strategy()
    s.cfg.pump_lookback_bars = 3
    s.cfg.pump_min_pct = 4.0
    s.cfg.vol_z_min = 0.0
    closes = [100.0, 100.5, 100.7, 101.0, 99.8]
    highs = [100.2, 101.0, 106.0, 105.0, 100.5]
    volumes = [100.0] * len(closes)
    is_pump, pct, _, _ = s._detect_pump(closes, highs, volumes)
    assert is_pump is True
    assert pct >= 4.0


def test_pair_arb_funding_cost_reduces_realizable_pnl():
    from scripts.validate_pair_arb import _gen_cointegrated
    from strategies.pair_stat_arb_v1 import compute_spread
    import statistics

    a, b = _gen_cointegrated(n=300, seed=1)
    _, _, spread = compute_spread(a[-120:], b[-120:])
    sd = statistics.pstdev(spread)
    a = list(a)
    a[-1] = a[-1] * math.exp(3.0 * sd)
    cfg = PairConfig(
        lookback=120,
        entry_z=1.5,
        exit_z=0.5,
        stop_z=10.0,
        max_half_life=999.0,
        min_abs_corr=0.6,
        max_beta_drift_frac=0.0,
    )
    no_funding = simulate_pair(a, b, cfg, fee_bps=0.0, max_hold_bars=1, funding_bps_per_8h=0.0)
    with_funding = simulate_pair(a, b, cfg, fee_bps=0.0, max_hold_bars=1, funding_bps_per_8h=80.0)
    assert no_funding and with_funding
    assert with_funding[0]["pnl"] < no_funding[0]["pnl"]
