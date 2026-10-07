import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import wf as W, replay as P
H = P.H; T0 = W.ms("2023-01-02")

def _mir():
    rng = np.random.default_rng(3); tr = []; metki = {}
    for k in range(24 * 600):
        metki[T0 + k * H] = "BULL_TREND" if (k // 500) % 2 == 0 else "BEAR_TREND"
    for k in range(0, 24 * 600, 7):
        st = metki[T0 + k * H]
        tr.append(dict(leg="L", sym=f"S{k % 50}", side="long", ts=T0 + k * H, R=(0.5 if st == "BULL_TREND" else -0.5) + rng.normal(0, .1), hours=3))
        tr.append(dict(leg="M", sym=f"Q{k % 50}", side="short", ts=T0 + k * H, R=-0.3 + rng.normal(0, .1), hours=3))
    return tr, metki

def test_srodstvo_nahodit_rezhim_i_otklyuchaet_plohuyu_nogu():
    tr, m = _mir(); s = W.srodstvo(tr, m, T0, T0 + 24 * 300 * H)
    assert s["L"] == ["BULL_TREND"] and s["M"] == []

def test_filtr_nog():
    tr, m = _mir(); f = W.filtr_nog(tr, T0, T0 + 24 * 300 * H)
    assert "M" not in f

def test_ruki_i_verdikt_na_sinteticheskom_mire():
    tr, m = _mir()
    konf = dict(slotov=12, sgiby=[["2023-01-02", "2023-06-01", "2023-08-01"], ["2023-01-02", "2023-08-01", "2023-10-01"],
                                 ["2023-01-02", "2023-10-01", "2023-12-01"], ["2023-01-02", "2023-12-01", "2024-02-01"]])
    r = W.prognat(tr, m, konf)
    assert r["summa_R"]["C"] > r["summa_R"]["A"] and r["verdikt"] == "B3_PASS"

def test_konfig_zamorozhen_i_chitaem():
    import json; k = json.loads(W.KONF.read_text()); assert k["slotov"] == 12 and len(k["sgiby"]) == 4
