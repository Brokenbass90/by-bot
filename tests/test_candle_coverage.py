import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.candle_coverage import assess_coverage, assess_universe

H = 3_600_000  # 1h in ms


def _bars(n, start=0, step=H, flat_every=0):
    rows = []
    for i in range(n):
        px = 100.0 + i * 0.1
        hi, lo = px + 1.0, px - 1.0
        if flat_every and i % flat_every == 0:
            hi = lo = px
        rows.append([start + i * step, px, hi, lo, px, 10.0])
    return rows


def test_clean_series_passes():
    r = assess_coverage(_bars(500), interval_min=60)
    assert r.ok
    assert r.coverage == 1.0
    assert r.n_gaps == 0


def test_short_series_fails():
    r = assess_coverage(_bars(50), interval_min=60)
    assert not r.ok
    assert any("too_few_bars" in x for x in r.reasons)


def test_holes_detected_and_fail_gate():
    rows = _bars(300) + _bars(200, start=350 * H)  # 50-bar hole
    r = assess_coverage(rows, interval_min=60)
    assert not r.ok
    assert r.n_gaps == 1
    assert r.max_gap_bars == 50
    assert any("gap_over" in x for x in r.reasons)
    assert r.coverage < 0.995


def test_flat_bars_fail_gate():
    r = assess_coverage(_bars(500, flat_every=5), interval_min=60)  # 20% flat
    assert not r.ok
    assert any("flat_share" in x for x in r.reasons)


def test_duplicates_fail_gate():
    rows = _bars(300)
    rows.insert(100, list(rows[100]))  # duplicate ts
    r = assess_coverage(rows, interval_min=60)
    assert not r.ok
    assert r.dup_bars == 1


def test_non_monotonic_fails():
    rows = _bars(300)
    rows[150][0] = rows[10][0]
    r = assess_coverage(rows, interval_min=60)
    assert not r.ok
    assert "non_monotonic_ts" in r.reasons


def test_universe_gate():
    uni = {
        "GOODA": _bars(500),
        "GOODB": _bars(500),
        "GOODC": _bars(500),
        "HOLEY": _bars(300) + _bars(100, start=400 * H),
        "EMPTY": [],
    }
    out = assess_universe(uni, interval_min=60, min_ok_symbols=3)
    assert out["go"] is True
    assert out["ok_symbols"] == ["GOODA", "GOODB", "GOODC"]
    assert "HOLEY" in out["failed"] and "EMPTY" in out["failed"]

    out2 = assess_universe({"HOLEY": uni["HOLEY"], "EMPTY": []}, min_ok_symbols=1)
    assert out2["go"] is False


def test_fx_weekend_closure_not_a_hole():
    # 5 trading days, weekend (48 bars H1), 5 more days
    week1 = _bars(120)
    week2 = _bars(120, start=(120 + 48) * H)
    rows = week1 + week2
    r_crypto = assess_coverage(rows, interval_min=60)  # 24/7: weekend IS a hole
    assert not r_crypto.ok
    r_fx = assess_coverage(rows, interval_min=60, market_closure_gap_bars=40)
    assert r_fx.ok
    assert r_fx.coverage == 1.0
    assert r_fx.n_gaps == 0


def test_fx_real_hole_still_caught_with_closure_mode():
    week1 = _bars(120)
    hole_then_week2 = _bars(100, start=(120 + 48 + 20) * H)  # weekend + 20-bar hole
    rows = week1 + hole_then_week2
    r = assess_coverage(rows, interval_min=60, market_closure_gap_bars=40)
    # 68-bar gap >= closure threshold -> swallowed as closure; but a separate
    # real hole below threshold must still fail:
    rows2 = _bars(120) + _bars(30, start=(120 + 20) * H) + _bars(100, start=(120 + 20 + 30 + 48) * H)
    r2 = assess_coverage(rows2, interval_min=60, market_closure_gap_bars=40)
    assert not r2.ok
    assert any("gap_over" in x or "coverage_below" in x for x in r2.reasons)
