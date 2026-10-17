import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kontekst_v2 as K

H = K.H


def bary(n, drift=0.0, seed=1):
    rng = np.random.default_rng(seed); c = 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.003, n)))
    return [[i * H, c[i], c[i], c[i], c[i], 1.0] for i in range(n)]


class T(unittest.TestCase):
    def test_prichinnost(self):
        b = bary(1200); t = 1000 * H
        self.assertEqual(K.rezhim(t, b[:1000]), K.rezhim(t, b))           # будущие бары не меняют режим

    def test_trend_i_bokovik(self):
        self.assertEqual(K.rezhim(1200 * H, bary(1200, drift=0.002))["rezhim_v2"], "TREND_UP")
        self.assertEqual(K.rezhim(1200 * H, bary(1200, drift=-0.002))["rezhim_v2"], "TREND_DOWN")
        self.assertIn(K.rezhim(1200 * H, bary(1200))["rezhim_v2"], ("BOKOVIK", "NEYASNO"))

    def test_malo_dannyh(self):
        self.assertEqual(K.rezhim(100 * H, bary(100))["rezhim_v2"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
