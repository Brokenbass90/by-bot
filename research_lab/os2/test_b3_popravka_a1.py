"""Регрессии на 4 находки OS2_FOUNDATION_AUDIT_2026_10_07 (Codex)."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay as P, wf as W, rezhim_v1 as R
H = P.H; T0 = 1700000000000 // (4 * H) * (4 * H)

def test_1_pervaya_poterya_v_prosadke():
    r = P.prognat([dict(leg="A", sym="X", side="long", ts=T0, R=-2.0, hours=1)], {}, None, okno=(T0, T0 + 10 * H))
    assert r["prosadka_R"] == 2.0

def test_2_v_obuchenie_tolko_zakrytye_isxody():
    tr = [dict(leg="L", sym=f"S{i}", side="long", ts=T0 + i * H, R=1.0, hours=336) for i in range(30)]
    m = {T0 + k * H: "BULL_TREND" for k in range(400)}
    assert W.srodstvo(tr, m, T0, T0 + 40 * H) == {} and W.filtr_nog(tr, T0, T0 + 40 * H) == {}
    assert W.srodstvo(tr, m, T0, T0 + 400 * H) == {"L": ["BULL_TREND"]}

def test_3_nepolnyy_4h_bar_ne_prinimaetsya():
    ts = T0 + np.array([0, 1, 2, 4, 5, 6, 7]) * H          # в первом 4h-баре нет часа +3
    o = np.ones((len(ts), 5))
    rows = R.agg4h(ts, o); assert [r[0] for r in rows] == [T0 + 4 * H]

def test_3b_dyra_daet_unknown():
    n = 24 * 30; ts = T0 + np.arange(n) * H; o = np.column_stack([np.linspace(1, 2, n)] * 4 + [np.ones(n)])
    s_full = R.metki(ts, o); keep = np.ones(n, bool); keep[n - 30] = False
    s_gap = R.metki(ts[keep], o[keep])
    assert s_full[-1] is not None and s_gap[-1] is None

def test_4_skvoznaya_prosadka_mezhdu_sgibami():
    assert W.nepreryvnaya_prosadka([2, -1, -1, -1, 2]) == 3.0
