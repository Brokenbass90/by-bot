import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shablony_v2 as S


class D:
    t0, t1 = 1_700_000_000_000, 1_700_000_000_000 + 20000 * 3_600_000


class T(unittest.TestCase):
    def test_chas_shum_i_moshchnost(self):
        lozh = sum(abs(S.odin_aktiv_chas(dict(sintetika=dict(seed=s, n=6000), priznak="chas", chas=14, znak=1, hold=4, izderzhki_bps=0), D)["t"]) > 2.5
                   for s in range(30))
        self.assertLessEqual(lozh, 2, "шум не должен давать находок")
        r = S.odin_aktiv_chas(dict(sintetika=dict(seed=1, n=6000, chas=14, edge_bps=60, hold=4), priznak="chas", chas=14, znak=1, hold=4, izderzhki_bps=0), D)
        self.assertGreater(r["t"], 3.0); self.assertEqual(len(r["metrika"]["polovinki_bps"]), 2)
        r2 = S.odin_aktiv_chas(dict(sintetika=dict(seed=1, n=6000, chas=14, edge_bps=60, hold=4), priznak="chas", chas=14, znak=1, hold=4, izderzhki_bps=200), D)
        self.assertLess(r2["metrika"]["edge_bps"], r["metrika"]["edge_bps"] - 199)        # издержки вычитаются явно

    def test_sobytie(self):
        lozh = sum(abs(S.sobytie(dict(sintetika=dict(seed=s, n=6000, sobytiy=150), posle=6, znak=1, izderzhki_bps=0), D)["t"]) > 2.5 for s in range(20))
        self.assertLessEqual(lozh, 2)
        r = S.sobytie(dict(sintetika=dict(seed=3, n=6000, sobytiy=150, edge_bps=80), posle=6, znak=1, izderzhki_bps=10), D)
        self.assertGreater(r["t"], 3.0); self.assertIn("syroy_posle_izderzhek_bps", r["metrika"])

    def test_okno_zabor(self):
        class D2: t0, t1 = D.t0, D.t0 + 100 * 3_600_000
        r = S.odin_aktiv_chas(dict(sintetika=dict(seed=1, n=6000), priznak="chas", chas=3, znak=1, hold=2, izderzhki_bps=0), D2)
        self.assertLessEqual(r["n"], 5)


if __name__ == "__main__":
    unittest.main()


class TZnak(unittest.TestCase):
    def test_sobytie_znak_sobytiya_17_10(self):
        """Знак события: −1 переворачивает доход события и контролей; без поля поведение прежнее."""
        import numpy as np
        from types import SimpleNamespace
        ts = (np.arange(400) * 3600_000).astype(np.int64); c = 100 * np.exp(np.cumsum(np.full(400, 0.001)))
        o = np.concatenate([[100.0], c[:-1]]); bary = np.c_[ts, o, c, c, c]
        orig = S._bary; S._bary = lambda s, d, sint=None: bary
        try:
            dost = SimpleNamespace(t0=0, t1=10**13)
            sob = [dict(t_ms=int(ts[i]), simvol="X") for i in (60, 160, 260)]
            base = dict(posle=5, znak=1, izderzhki_bps=0, kontrol_k=3, sobytiya=sob)
            r1 = S.sobytie(base, dost)
            r2 = S.sobytie(dict(base, sobytiya=[dict(e, znak=-1) for e in sob]), dost)
            r0 = S.sobytie(dict(base, sobytiya=[dict(e, znak=1) for e in sob]), dost)
            self.assertGreater(r1["metrika"]["syroy_posle_izderzhek_bps"], 0)
            self.assertEqual(r1["metrika"]["syroy_posle_izderzhek_bps"], r0["metrika"]["syroy_posle_izderzhek_bps"])
            self.assertEqual(r2["metrika"]["syroy_posle_izderzhek_bps"], -r1["metrika"]["syroy_posle_izderzhek_bps"])
        finally:
            S._bary = orig
