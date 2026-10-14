import sys, unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kalibrovka_mozga as M


class TestMozg(unittest.TestCase):
    def test_auc(self):
        y = np.array([0, 0, 1, 1.]); self.assertEqual(M.auc(y, np.array([1, 2, 3, 4.])), 1.0); self.assertEqual(M.auc(y, np.array([4, 3, 2, 1.])), 0.0)

    def test_shum_i_nestabil_ne_prohodyat_silnyy_prohodit(self):
        rng = np.random.default_rng(1)
        self.assertFalse(M.test(*M.sintetika("SHUM", 900, rng), rng)[0])
        self.assertFalse(M.test(*M.sintetika("NESTABIL", 900, rng), rng)[0])
        self.assertTrue(M.test(*M.sintetika("STABIL_0.70", 1376, rng), rng)[0])


if __name__ == "__main__":
    unittest.main()
