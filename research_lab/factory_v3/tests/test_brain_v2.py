import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import brain_v2 as B

def baza(v, otkr): return 1.0, []
def V(**k):
    d = dict(sleeve="KITY", symbol="SOLUSDT", side="long", context=dict(rezhim_v1="NEUTRAL", kontekst_v2={}))
    d.update(k); return d
def O(**k):
    d = dict(sleeve="KITY", symbol="SOLUSDT", side="long"); d.update(k); return d

class T(unittest.TestCase):
    def test_trade(self):
        self.assertEqual(B.brain_v2_det(V(), [], baza), (1.0, ["TRADE"]))
    def test_konflikt(self):
        u, p = B.brain_v2_det(V(), [(O(sleeve="ETF", side="short"), 1.0)], baza); self.assertEqual((u, p[0]), (0.0, "ABSTAIN"))
    def test_hedge_razreshen_pri_konflikte(self):
        u, p = B.brain_v2_det(V(sleeve="ELDER", side="short"), [(O(), 1.0)], baza); self.assertEqual((u, p[0]), (1.0, "HEDGE"))
    def test_hedge_bull(self):
        v = V(sleeve="ELDER", side="short", context=dict(rezhim_v1="BULL_TREND", kontekst_v2={}))
        self.assertEqual(B.brain_v2_det(v, [], baza)[0], 0.0)
    def test_makro(self):
        v = V(context=dict(kontekst_v2=dict(makro_cherez_ch=1.5)))
        self.assertEqual(B.brain_v2_det(v, [], baza), (0.0, ["ABSTAIN", "makro_cherez_1.5ch"]))
    def test_vol(self):
        v = V(context=dict(kontekst_v2=dict(vol_pct_720=0.97)))
        self.assertEqual(B.brain_v2_det(v, [], baza)[0], 0.5)
    def test_net_cap(self):
        otkr = [(O(symbol=f"X{i}"), 1.0) for i in range(3)]
        self.assertEqual(B.brain_v2_det(V(), otkr, baza), (0.0, ["ABSTAIN", "net_cap"]))
        otkr = [(O(symbol=f"X{i}"), 1.0) for i in range(2)] + [(O(symbol="Y", side="short"), 0.5)]
        self.assertEqual(B.brain_v2_det(V(), otkr, baza)[0], 1.0)
    def test_unknown_kontekst_ne_lomaet(self):
        v = V(context=dict(kontekst_v2=dict(makro_cherez_ch="UNKNOWN", vol_pct_720="UNKNOWN")))
        self.assertEqual(B.brain_v2_det(v, [], baza)[0], 1.0)

if __name__ == "__main__":
    unittest.main()
