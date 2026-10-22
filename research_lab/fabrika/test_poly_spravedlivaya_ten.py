import math, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import poly_spravedlivaya_ten as P


class T(unittest.TestCase):
    def test_model_atm(self):
        p, phi, d2 = P.model(100.0, 100.0, 0.5, 1 / 365); self.assertAlmostEqual(p, 0.5, 1)
        p2, _, _ = P.model(110.0, 100.0, 0.5, 1 / 365); self.assertGreater(p2, 0.99)

    def test_reshenie_storona(self):
        # справедливо 0.30, YES продают за 0.40 → покупать NO за ~0.60 выгодно
        d = P.reshit(0.30, 0.35, 0.5, 1 / 365, vw_yes=0.40, vw_no=0.60); self.assertEqual(d["storona"], "NO")
        self.assertGreater(d["ev_NO_stress"], 0); self.assertLess(d["ev_YES_stress"], 0)
        # цены рядом со справедливой → расходы съедают → входа нет
        d = P.reshit(0.30, 0.35, 0.5, 1 / 365, vw_yes=0.305, vw_no=0.70); self.assertIsNone(d["storona"])

    def test_bez_zamorozki_resheniy_net(self):
        self.assertEqual(P.resheniya(set(), {"x": dict(vopros="Will the price of Bitcoin be above $80,000 on October 23?", t=1)}, 0), [])


if __name__ == "__main__":
    unittest.main()
