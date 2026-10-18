import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ispolnimost as V2
import ispolnimost_v21 as I


def _atlas(tmp, **z):
    p = tmp / "A.json"; p.write_text(json.dumps({"atlas": z})); V2._kesh.clear(); return p


def test_regress_v2_zoloto_slepoe():
    """Регрессия старых ворот: стоп 0.3 % на золоте в V2 всегда отвергался (это и есть дефект)."""
    assert V2.dopusk("XAUUSD", 0.003, 3.0, False)[1] == "infeasible_stop_lev"


def test_g1_zoloto_fx():
    assert I.dopusk("XAUUSD", 0.003, 3.0, "gold_glub")[0] is True            # L = 0.01/0.003 = 3.3 ≤ 20; cost 6/30 = 0.2R
    assert I.dopusk("XAUUSD", 0.0004, 1.0, "gold")[1] == "lev_instr"         # L = 25 > 20
    assert I.dopusk("EURUSD", 0.0004, 0.5, "fx7")[0] is True                 # L = 25 ≤ 30; cost 1/4 = 0.25R (граница)
    assert I.dopusk("EURUSD", 0.0003, 1.0, "fx7")[1] == "lev_instr"          # L = 33 > 30


def test_g3_ne_izmenilsya_v_R(tmp_path):
    """Издержки в R совпадают с V2 для одной и той же сделки (размер позиции на R не влияет)."""
    p = _atlas(tmp_path, AAA={"n": 600, "glubina_med_usd": 1e9, "spred_med_bps": 3.0})
    ok2, _, s2 = V2.dopusk("AAA", 1/50, 6.0, True, p)
    ok21, _, s21 = I.dopusk("AAA", 1/50, 6.0, "crypto137", p)
    assert ok2 and ok21 and abs(s2 - s21) < 1e-12
    q = _atlas(tmp_path, WIDE={"n": 900, "glubina_med_usd": 1e9, "spred_med_bps": 20.0})
    assert I.dopusk("WIDE", 1/80, 6.0, "crypto137", q)[1] == "cost_dominated"
    assert I.dopusk("WIDE", 1/70, 6.0, "crypto137", q)[0] is True


def test_glubina_ot_razmera_zayavki(tmp_path):
    p = _atlas(tmp_path, MEL={"n": 600, "glubina_med_usd": 200.0, "spred_med_bps": 2.0},
               MAL={"n": 10, "glubina_med_usd": 1e9, "spred_med_bps": 1.0})
    assert I.dopusk("MEL", 0.06, 6.0, "crypto137", p)[0] is True            # N = 10/0.06 = 167 ≤ 200
    assert I.dopusk("MEL", 0.04, 6.0, "crypto137", p)[1] == "depth_lt_order"  # N = 250 > 200
    assert I.dopusk("MEL", 0.04, 6.0, "crypto137", p, kapital=300)[0] is True  # N = 75 при капитале 300
    assert I.dopusk("MAL", 0.06, 6.0, "crypto137", p)[1] == "atlas_net"
    assert I.dopusk("NET", 0.06, 6.0, "crypto137", p)[1] == "atlas_net"
