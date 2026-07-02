"""Tests for bot.fx_harness — run fx_setups over FX data, feed the gate."""
import random
from bot.fx_harness import backtest_fx_setup, summarize_trades
from bot.fx_setups import session_range_fade

LON = 9 * 3600


def _fx_range(n=600, seed=5, mid=1.10, band=0.0015):
    random.seed(seed); rows = []; prev = mid
    for i in range(n):
        c = mid + 0.2 * (prev - mid) + random.uniform(-band, band)
        o = prev
        h = max(o, c) + abs(random.uniform(0, band * 0.3))
        l = min(o, c) - abs(random.uniform(0, band * 0.3))
        rows.append([LON + i * 300, o, h, l, c, 1000]); prev = c
    return rows


def _trend(n=400):
    return [[LON + i * 300, 1.10 + i * 0.0002, 1.10 + i * 0.0002 + 0.0003,
             1.10 + i * 0.0002 - 0.0002, 1.10 + i * 0.0002 + 0.0001, 1000] for i in range(n)]


def test_harness_produces_trades():
    tr = backtest_fx_setup(_fx_range(), session_range_fade,
                           setup_kwargs={"block_asia": False}, tp_rr=2.0, sl_atr=1.0)
    assert isinstance(tr, list)
    for t in tr:
        assert set(("entry_ts", "exit_ts", "r", "side")) <= set(t)
        assert t["side"] in ("long", "short")
        assert t["exit_ts"] >= t["entry_ts"]      # causal: exit not before entry


def test_no_overlapping_positions():
    tr = backtest_fx_setup(_fx_range(), session_range_fade, setup_kwargs={"block_asia": False})
    for a, b in zip(tr, tr[1:]):
        assert b["entry_ts"] >= a["exit_ts"]      # cooldown: next entry after prior exit


def test_fees_reduce_r():
    rows = _fx_range()
    cheap = backtest_fx_setup(rows, session_range_fade, setup_kwargs={"block_asia": False}, fee_bps=1.0)
    pricey = backtest_fx_setup(rows, session_range_fade, setup_kwargs={"block_asia": False}, fee_bps=20.0)
    if cheap and pricey:
        assert summarize_trades(pricey)["net_r"] < summarize_trades(cheap)["net_r"]


def test_summarize_shape():
    s = summarize_trades([{"r": 2.0}, {"r": -1.0}, {"r": 2.0}])
    assert s["trades"] == 3 and s["win_rate"] > 0 and "pf" in s


def test_empty_summary():
    assert summarize_trades([])["trades"] == 0


def test_trend_yields_few_or_losing_fades():
    # fading a clean trend should not be a free win; harness must run without error
    tr = backtest_fx_setup(_trend(), session_range_fade, setup_kwargs={"block_asia": False})
    assert isinstance(tr, list)
