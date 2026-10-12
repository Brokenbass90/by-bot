import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ispolnimost as I

def _atlas(tmp, **z):
    p = tmp / "A.json"; p.write_text(json.dumps({"atlas": z})); I._kesh.clear(); return p

def test_g1_granica():
    assert I.dopusk("X", 1/100, 1.0, False)[0] is True
    assert I.dopusk("X", 1/100.01, 1.0, False)[1] == "infeasible_stop_lev"
    assert I.dopusk("X", 1e-7, 1.0, False)[1] == "infeasible_stop_lev"      # ATR→0 (класс SF3 GRASS)
    assert I.dopusk("X", 0.0, 1.0, False)[1] == "infeasible_stop_lev"

def test_g3_kripto_atlas(tmp_path):
    p = _atlas(tmp_path, AAA={"n": 600, "glubina_med_usd": 5000, "spred_med_bps": 3.0},
               MEL={"n": 600, "glubina_med_usd": 200, "spred_med_bps": 1.0}, MAL={"n": 10, "glubina_med_usd": 9e9, "spred_med_bps": 1.0})
    ok, pr, sR = I.dopusk("AAA", 1/50, 6.0, True, p); assert ok and abs(sR - 0.015) < 1e-12        # 50·15bps = 0.075R
    assert I.dopusk("AAA", 1/100, 6.0, True, p)[0] is True                                          # 100·15bps = 0.15R
    assert I.dopusk("NET", 1/10, 6.0, True, p)[1] == "atlas_net"
    assert I.dopusk("MEL", 1/10, 6.0, True, p)[1] == "atlas_net"
    assert I.dopusk("MAL", 1/10, 6.0, True, p)[1] == "atlas_net"

def test_g3_cost_dominated(tmp_path):
    p = _atlas(tmp_path, WIDE={"n": 900, "glubina_med_usd": 5000, "spred_med_bps": 20.0})
    assert I.dopusk("WIDE", 1/80, 6.0, True, p)[1] == "cost_dominated"                             # 80·32bps = 0.256R
    assert I.dopusk("WIDE", 1/70, 6.0, True, p)[0] is True                                          # 70·32bps = 0.224R

def test_ne_kripto_bez_atlasa():
    I._kesh.clear(); ok, pr, sR = I.dopusk("EURUSD", 1/100, 1.0, False, Path("/net/takogo")); assert ok and sR == 0.0
