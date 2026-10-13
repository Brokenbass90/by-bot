import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reestr_v1 import Reestr
import sudi_v_reestr as M


class TestSudi(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); self.r = Reestr(self.d / "r.jsonl")
        self.r.semya("KITY", "x"); self.r.gipoteza("KITY_M3_BYBIT_TEN", "KITY", "x", []); self.r.nasledie("KITY_M3_BYBIT_TEN", "SHADOW", "P.md")
        M.HERE = self.d; M.D = self.d / "data"

    def nedelya(self, d, c1, c2):
        p = self.d / "data" / "kity_bybit_ten" / d; p.mkdir(parents=True, exist_ok=True)
        (p / "kvitanciya_C1.json").write_text(json.dumps(dict(status=c1)))
        if c2: (p / "paritet_C2.json").write_text(json.dumps(dict(status=c2)))

    def test_kity_idempotentno_i_kanareyka(self):
        self.nedelya("2026-10-15", "OPERATIONAL_PASS", "C2_PASS")
        self.assertEqual(M.kity(self.r), 2); self.assertEqual(M.kity(self.r), 0)          # повтор не дублирует
        self.assertFalse(M.gotovnost_kanareyki_kity(self.r)["gotovo_k_dosie"])
        self.nedelya("2026-10-22", "OPERATIONAL_PASS", None)
        M.kity(self.r); self.assertFalse(M.gotovnost_kanareyki_kity(self.r)["gotovo_k_dosie"])   # нет C2
        self.nedelya("2026-10-22", "OPERATIONAL_PASS", "C2_PASS"); M.kity(self.r)
        g = M.gotovnost_kanareyki_kity(self.r)
        self.assertTrue(g["gotovo_k_dosie"]); self.assertEqual(g["nedeli"], ["2026-10-15", "2026-10-22"])

    def test_fail_ne_daet_gotovnosti(self):
        self.nedelya("2026-10-15", "OPERATIONAL_FAIL", "C2_PASS"); self.nedelya("2026-10-22", "OPERATIONAL_PASS", "C2_PASS")
        M.kity(self.r); self.assertEqual(M.gotovnost_kanareyki_kity(self.r)["chistyh_nedel"], 1)

    def test_kvitanciya_ne_menyaet_status(self):
        self.nedelya("2026-10-15", "OPERATIONAL_FAIL", "C2_FAIL"); M.kity(self.r)
        self.assertEqual(self.r.sostoyanie()["gipotezy"]["KITY_M3_BYBIT_TEN"]["status"], "SHADOW")


if __name__ == "__main__":
    unittest.main()
