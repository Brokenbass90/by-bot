import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dubl_proverka as D


class T(unittest.TestCase):
    S = {"semi": {"FUNDING_CARRY_XS": {"status": "KILL", "opisanie": "пачка 1"}, "TOLPA_XS": {"status": "KILL", "opisanie": "x"},
                  "ETF_PREMIYA": {"status": "ACTIVE", "opisanie": "etf ibit премия"}}, "gipotezy": {}}

    def test_fanding_kross_pojman(self):
        r = D.najti("FANDING_KROSS кросс-секция: монеты с крайним фандингом относительно остальных (перекос толпы)", self.S)
        self.assertIn("FUNDING_CARRY_XS", [x[0] for x in r])

    def test_aktivnye_ne_meshayut(self):
        self.assertEqual(D.najti("ETF ibit премия новый вариант", self.S), [])

    def test_raznoe_ne_lovit(self):
        self.assertEqual(D.najti("STOP_HVOST выход по пути цены", self.S), [])
