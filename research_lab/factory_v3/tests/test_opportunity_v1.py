import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import opportunity_v1 as O


class TestOpp(unittest.TestCase):
    def test_prichinnost_i_kruglyy_put(self):
        with self.assertRaises(O.NarushenieVremeni): O.zapis(10, 11, 12, "X", "m", "v1", 1, 1.0, 0.0012, {})   # признаки из будущего
        with self.assertRaises(O.NarushenieVremeni): O.zapis(10, 9, 8, "X", "m", "v1", 1, 1.0, 0.0012, {})    # вход раньше решения
        z = O.zapis(10, 9, 12, "X", "m", "v1", -1, 2.5, 0.0012, {"a": 1}, 20, 2.4, 0.0, 0.03)
        p = Path(tempfile.mkdtemp()) / "t.csv.gz"; O.zapisat(p, [z]); r = O.prochitat(p)
        self.assertEqual(r[0]["simvol"], "X"); self.assertTrue((p.parent / "t.schema.json").exists())


if __name__ == "__main__":
    unittest.main()
