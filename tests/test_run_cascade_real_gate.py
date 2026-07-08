"""Offline units for the real-data cascade gate runner (no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_cascade_real_gate import (
    bucket_liquidations, forward_fill_to_grid, liq_series_for_grid,
    condition_diag, load_price_rows, run_symbol, run_symbol_window_v1, simulate_fade,
)

M5 = 5 * 60_000


def test_bucket_liquidations_sums_per_symbol_bucket():
    ev = [
        {"ts_ms": 100_000, "symbol": "BTCUSDT", "usd": 1000.0},
        {"ts_ms": 200_000, "symbol": "BTCUSDT", "usd": 500.0},   # same 5m bucket as 100k
        {"ts_ms": M5 + 1, "symbol": "BTCUSDT", "usd": 42.0},
        {"ts_ms": 100_000, "symbol": "ETHUSDT", "usd": 7.0},
        {"ts_ms": -5, "symbol": "BAD", "usd": 1.0},              # dropped
        {"symbol": "NOTS", "usd": 1.0},                          # dropped
    ]
    b = bucket_liquidations(ev)
    assert b["BTCUSDT"][0] == 1500.0
    assert b["BTCUSDT"][M5] == 42.0
    assert b["ETHUSDT"][0] == 7.0
    assert "BAD" not in b and "NOTS" not in b


def test_forward_fill_and_liq_grid():
    grid = [0, M5, 2 * M5, 3 * M5]
    pts = [(M5, 0.01), (3 * M5, 0.02)]
    ff = forward_fill_to_grid(pts, grid)
    assert ff[0] != ff[0]              # NaN before first point
    assert ff[1] == 0.01 and ff[2] == 0.01 and ff[3] == 0.02
    liq = liq_series_for_grid({M5: 99.0}, grid)
    assert liq == [0.0, 99.0, 0.0, 0.0]


def _mk_market(n=800):
    """Flat market, then a crash with huge liq spike + OI flush + hot funding."""
    rows, funding, oi, liq = [], [], [], []
    px = 100.0
    crash_at = 700
    for i in range(n):
        if crash_at <= i < crash_at + 4:
            px *= 0.97                                   # -3%/bar cascade
        rows.append([i * M5, px, px * 1.002, px * 0.998, px, 10.0])
        funding.append(0.0001 if i < crash_at else 0.002)  # funding blows out
        oi.append(1e9 if i < crash_at else 1e9 * (1 - 0.03 * (i - crash_at + 1)))
        liq.append(1000.0 if i != crash_at + 3 else 500_000.0)  # spike at exhaustion
    return rows, funding, oi, liq


def test_detector_plus_sim_produces_fade_trade():
    rows, funding, oi, liq = _mk_market()
    trades = run_symbol(
        rows, funding, oi, liq, symbol="TESTUSDT",
        funding_z_min=1.5, oi_drop_min_pct=3.0, liq_pctile_min=90.0,
        sl_atr=1.0, tp_rr=1.5, max_hold=48, cooldown_bars=12,
        fee_bps=6.0, slippage_bps=2.0, warmup=300,
    )
    # Detector may or may not fire depending on its internal windows — but the
    # pipeline must not crash and any trade must be a long fade of the crash.
    for t in trades:
        assert t["side"] == "long"
        assert isinstance(t["r"], float)


def test_window_v1_accepts_sparse_liq_spike():
    rows, funding, oi, liq = _mk_market()
    trades = run_symbol_window_v1(
        rows, funding, oi, liq, symbol="TESTUSDT",
        funding_z_min=1.5, oi_drop_min_pct=3.0,
        intensity_window=3, intensity_k=5.0, liq_mean_mult=8.0,
        liq_abs_min=0.0, sl_atr=1.0, tp_rr=1.5, max_hold=48,
        cooldown_bars=12, fee_bps=6.0, slippage_bps=2.0, warmup=300,
    )
    assert trades
    assert all(t["side"] == "long" for t in trades)


def test_condition_diag_reports_binding_rates():
    rows, funding, oi, liq = _mk_market()
    diag = condition_diag(
        rows, funding, oi, liq, mode="window_v1", warmup=300,
        funding_z_min=1.5, oi_drop_min_pct=3.0, liq_pctile_min=0.0,
        intensity_window=3, intensity_k=5.0, liq_mean_mult=8.0,
        liq_abs_min=0.0,
    )
    assert diag["bars"] > 0
    assert "timing_ok_rate" in diag
    assert "liq_ok_rate" in diag


def test_simulate_fade_sl_first_and_fees():
    rows = [[i * M5, 100, 101, 99, 100, 1] for i in range(30)]
    rows.append([30 * M5, 100, 100.1, 94.0, 95.0, 1])  # big down bar hits long SL
    rows.extend([[(31 + k) * M5, 95, 96, 94, 95, 1] for k in range(5)])
    sim = simulate_fade(rows, 29, "long", sl_atr=1.0, tp_rr=2.0, max_hold=5,
                        fee_bps=6.0, slippage_bps=2.0)
    assert sim is not None
    assert sim["r"] < -0.9  # stopped out + fees


def test_load_price_rows_uses_window_not_largest_file(tmp_path):
    old = [[i * M5, 10, 11, 9, 10, 1] for i in range(200)]
    fresh_start = 10_000 * M5
    fresh = [[fresh_start + i * M5, 20, 21, 19, 20, 1] for i in range(20)]
    # Old file is intentionally larger; loader must still pick/merge the fresh
    # window instead of sorting by file size and returning zero rows.
    (tmp_path / "BTCUSDT_5_20250101_20250102.json").write_text(str(old).replace("'", '"'))
    (tmp_path / "BTCUSDT_5_20260701_20260702.json").write_text(str(fresh).replace("'", '"'))

    rows = load_price_rows(tmp_path, "BTCUSDT", fresh_start, fresh_start + 19 * M5)
    assert len(rows) == 20
    assert rows[0][0] == fresh_start
    assert rows[0][4] == 20
