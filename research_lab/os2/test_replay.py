import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay as P
H = P.H; T0 = 1700000000000 // H * H

def _sd():
    return [dict(leg="A", sym="X", side="long", ts=T0, R=1.0, hours=5), dict(leg="B", sym="Y", side="short", ts=T0 + H, R=-1.0, hours=2),
            dict(leg="A", sym="X", side="long", ts=T0 + 2 * H, R=2.0, hours=1), dict(leg="B", sym="Z", side="short", ts=T0 + 10 * H, R=0.5, hours=1)]

def _m(): return {T0 + k * H: ("BULL_TREND" if k < 5 else "BEAR_TREND") for k in range(20)}

def test_razreshayushchaya_politika_ravna_always_on():
    a = P.prognat(_sd(), _m(), None, okno=(T0, T0 + 100 * H)); b = P.prognat(_sd(), _m(), {"A": ["BULL_TREND", "BEAR_TREND", "NEUTRAL"], "B": ["BULL_TREND", "BEAR_TREND", "NEUTRAL"]}, okno=(T0, T0 + 100 * H))
    assert a["itogo_R"] == b["itogo_R"] and a["sdelok"] == b["sdelok"]

def test_simvol_zanyat_i_slot():
    a = P.prognat(_sd(), _m(), None, okno=(T0, T0 + 100 * H))
    assert a["sdelok"] == 3 and a["prichiny"].get("symbol_overlap") == 1

def test_rezhim_rezhet():
    b = P.prognat(_sd(), _m(), {"A": ["BULL_TREND"], "B": ["NEUTRAL"]}, okno=(T0, T0 + 100 * H))
    assert b["po_nogam"] == {"A": {"sdelok": 1, "R": 1.0}} and b["prichiny"].get("zero_priority_score") == 2

def test_zapechatannoe_okno_zakryto():
    with pytest.raises(PermissionError):
        P.prognat(_sd(), _m(), None, okno=(T0, P.SEALED + H))
    pol = {"A": ["BULL_TREND"]}
    P.prognat(_sd(), _m(), pol, okno=(T0, P.SEALED + H), final=True, hesh_zamka=P.hesh_politiki(pol))
