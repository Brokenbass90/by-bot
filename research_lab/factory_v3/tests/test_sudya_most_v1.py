import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reestr_v1 import Reestr, OshibkaReestra
import sudya_most_v1 as M


class TestMost(unittest.TestCase):
    def setUp(self):
        self.r = Reestr(Path(tempfile.mkdtemp()) / "r.jsonl")
        self.r.semya("S", "x"); self.r.gipoteza("G", "S", "x", []); self.r.perehod("G", "SCREEN", "s")
        self.r.okno("DEV", "d", "2023-01-01", "2024-01-01", "DEV", byudzhet=10)
        self.r.semya("T", "y"); self.r.gipoteza("TEN", "T", "y", []); self.r.nasledie("TEN", "SHADOW", "PREREG.md")

    def test_sudit_registriruet_do_vyzova(self):
        vidno = {}
        def sudya():
            vidno["popytka_uzhe_v_reestre"] = "P1" in self.r.sostoyanie()["popytki"]
            return dict(t=2.5, n=40)
        z = M.sudit(self.r, "P1", "G", "DEV", "SCREEN", {"a": 1}, {"min_n": 20, "znak": "+"}, sudya)
        self.assertTrue(vidno["popytka_uzhe_v_reestre"]); self.assertEqual(z["verdikt"], "PASS")

    def test_upavshiy_sudya_tratit_byudzhet(self):
        def sudya(): raise RuntimeError("упал")
        with self.assertRaises(RuntimeError):
            M.sudit(self.r, "P1", "G", "DEV", "SCREEN", {"a": 1}, {"min_n": 20}, sudya)
        p = self.r.sostoyanie()["popytki"]["P1"]
        self.assertIsNone(p["rezultat"]); self.assertEqual(self.r.popytok_na_okne("DEV"), 1)

    def test_verdikt_teni(self):
        with self.assertRaises(OshibkaReestra): M.verdikt(self.r, "TEN", "KEEP", "")
        with self.assertRaises(OshibkaReestra): M.verdikt(self.r, "G", "KEEP", "doc")        # не тень
        with self.assertRaises(OshibkaReestra): M.verdikt(self.r, "TEN", "PASS", "doc")
        M.verdikt(self.r, "TEN", "CONTINUE", "doc"); M.verdikt(self.r, "TEN", "KILL", "doc2")
        g = self.r.sostoyanie()["gipotezy"]["TEN"]
        self.assertEqual(g["status"], "KILL"); self.assertEqual([v["znachenie"] for v in g["verdikty"]], ["CONTINUE", "KILL"])


if __name__ == "__main__":
    unittest.main()
