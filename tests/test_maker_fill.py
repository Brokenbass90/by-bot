"""Honest maker-fill: trade-through fills, touches don't, same-bar SL counted."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.maker_fill import simulate_limit_entry, simulate_maker_trade

H = 3_600_000


def _bar(i, o, h, l, c):
    return [i * H, o, h, l, c, 10.0]


def _base(n=30, px=100.0, rng=1.0):
    return [_bar(i, px, px + rng, px - rng, px) for i in range(n)]


def test_long_limit_fills_only_on_trade_through():
    rows = _base(30)
    # signal at 29; limit at 98.0. ATR~2 -> through = 0.1
    rows.append(_bar(30, 100, 100.5, 98.05, 99.0))   # touches 98.05 > 97.9 -> NO fill
    rows.append(_bar(31, 99, 99.5, 97.5, 98.5))      # goes through 97.9 -> FILL
    f_no = simulate_limit_entry(rows[:31], 29, "long", 98.0)
    assert not f_no.filled and f_no.reason == "expired_unfilled"
    f_yes = simulate_limit_entry(rows, 29, "long", 98.0)
    assert f_yes.filled and f_yes.fill_i == 31 and f_yes.entry == 98.0


def test_unfilled_expires_after_validity():
    rows = _base(30) + [_bar(30 + k, 100, 101, 99.5, 100) for k in range(15)]
    f = simulate_limit_entry(rows, 29, "long", 98.0, validity_bars=5)
    assert not f.filled and f.reason == "expired_unfilled"


def test_short_limit_fill_and_tp():
    rows = _base(30)
    rows.append(_bar(30, 100, 102.2, 99.8, 101.0))     # through 102.1 -> fill short @102
    rows.append(_bar(31, 101, 101.5, 97.8, 98.0))      # falls to TP (102-2*ATR=98 target region)
    tr = simulate_maker_trade(rows, 29, "short", 102.0, sl_atr=1.0, tp_rr=1.5, max_hold=10)
    assert tr is not None
    assert tr["side"] == "short" and tr["entry"] == 102.0
    assert tr["r"] > 1.0     # TP hit minus fees
    assert tr["wait_bars"] == 1


def test_same_fill_bar_stop_counts_as_loss():
    rows = _base(30)
    # long limit 98; fill bar crashes straight through the stop (98-2=96)
    rows.append(_bar(30, 100, 100.2, 95.0, 95.5))
    tr = simulate_maker_trade(rows, 29, "long", 98.0, sl_atr=1.0, tp_rr=2.0)
    assert tr is not None
    assert tr["r"] < -0.9    # SL-first on the fill bar, fees on top


def test_same_bar_tp_not_credited():
    rows = _base(30)
    # fill bar goes through the limit and then rockets: TP on the SAME bar must not count
    rows.append(_bar(30, 100, 105.0, 97.8, 104.5))
    rows.extend(_bar(31 + k, 104, 104.5, 103.5, 104) for k in range(12))
    tr = simulate_maker_trade(rows, 29, "long", 98.0, sl_atr=1.0, tp_rr=2.0, max_hold=10)
    assert tr is not None
    # exit is timeout mark-to-close (104) not instant TP; still strongly positive
    assert tr["exit_ts"] > tr["fill_ts"]
    assert tr["r"] > 1.0


def test_never_fills_returns_none():
    rows = _base(30) + [_bar(30 + k, 100, 101, 99.5, 100) for k in range(15)]
    assert simulate_maker_trade(rows, 29, "long", 95.0) is None
