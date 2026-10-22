import datetime as dt, json, sys, tempfile, types, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ocenshchiki_ezhednevno as O


class T(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp()); O.ZH, O.SOST = d / "zh.jsonl", d / "s.json"

    def test_raz_v_sutki_i_oshibka_vidna(self):
        ok = lambda f: types.SimpleNamespace(returncode=0 if f.startswith("pump4") else 1, stdout="x", stderr="boom")
        t = dt.datetime(2026, 10, 23, 7, tzinfo=dt.timezone.utc)
        r = O.prohod(t, ok); self.assertEqual(r["status"], "OSHIBKA"); self.assertEqual(r["plohie"], ["slope_hedge_vpered.py", "tsmom_long_ten.py", "poly_yes_verdikt.py", "poly_sprav_verdikt.py"])
        self.assertEqual(O.prohod(t, ok)["status"], "NE_SEGODNYA_ILI_UZHE")
        self.assertEqual(O.prohod(dt.datetime(2026, 10, 24, 5, tzinfo=dt.timezone.utc), ok)["status"], "NE_SEGODNYA_ILI_UZHE")


if __name__ == "__main__":
    unittest.main()
