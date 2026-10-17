import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import asm1_fiks_ten as T, asm1_h1_sdelki as A


class Test(unittest.TestCase):
    def setUp(self):
        z = np.load(Path(__file__).resolve().parents[1] / "data/h1/SOLUSDT.npz")
        self.ts = z["ts"].astype(np.int64); self.x = z["ohlcv"].astype(float)

    def test_sovpadaet_s_istoriey(self):
        """Решение тени на баре i = сигнал исторического прогона на том же баре (без будущих баров)."""
        ts, x = self.ts, self.x
        sig = A.signaly(ts, *[x[:, k] for k in range(5)])
        ib, s, a = sig[len(sig) // 2]
        lo = ib - 400
        r = T.reshit("SOLUSDT", ts[lo:ib + 1], *[x[lo:ib + 1, k] for k in range(5)], 0, int(ts[ib]) + 1000)
        self.assertIsNotNone(r); self.assertEqual((r["bar_ms"], r["storona"]), (int(ts[ib]), s)); self.assertFalse(r["pozdno"])

    def test_pozdno(self):
        ts, x = self.ts, self.x
        ib = A.signaly(ts, *[x[:, k] for k in range(5)])[5][0]; lo = ib - 400
        r = T.reshit("SOLUSDT", ts[lo:ib + 1], *[x[lo:ib + 1, k] for k in range(5)], 0, int(ts[ib]) + 2 * T.H)
        self.assertTrue(r["pozdno"])

    def test_ishod(self):
        ts, x = self.ts, self.x
        ib, s, a = A.signaly(ts, *[x[:, k] for k in range(5)])[10]
        r = dict(vhod_ms=int(ts[ib + 1]), storona=s, atr=a)
        R = T.ishod(r, ts, *[x[:, k] for k in range(4)])
        self.assertIsNotNone(R); self.assertGreaterEqual(R, -1.5)


if __name__ == "__main__":
    unittest.main()
