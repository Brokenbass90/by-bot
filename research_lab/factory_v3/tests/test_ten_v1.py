import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reestr_v1 import Reestr
import ten_v1 as T

H = 3_600_000


def okruzhenie(signal="ten_primery:kazhdyy_chas", status="SHADOW"):
    baza = Path(tempfile.mkdtemp()); r = Reestr(baza / "r.jsonl")
    r.semya("S", "x"); r.gipoteza("G", "S", "x", [])
    if status: r.nasledie("G", status, "PREREG.md")
    (baza / "factory_v3" / "teni").mkdir(parents=True)
    (baza / "factory_v3" / "teni" / "t1.json").write_text(json.dumps(dict(imya="t1", gipoteza="G", signal=signal, kazhdye_min=60)))
    return baza, r


class TestTen(unittest.TestCase):
    def test_bez_shadow_ne_startuet(self):
        baza, r = okruzhenie(status=None)
        with self.assertRaises(T.OshibkaTeni): T.Ten("t1", baza, r).zapusk(odin=True)

    def test_zhurnal_puls_idempotentnost_storozh(self):
        baza, r = okruzhenie(); t = T.Ten("t1", baza, r)
        t.zapusk(odin=True)
        a = t.prohod(now_ms=100 * H + 5); b = t.prohod(now_ms=100 * H + 10)          # тот же час — без дубля
        self.assertEqual(b["novyh"], 0)
        c = t.prohod(now_ms=101 * H + 5); self.assertEqual(c["novyh"], 1)
        self.assertIn("пульс: жив", (baza / "ten3_t1.log").read_text())
        self.assertIn("ten3_t1", json.loads((baza / "storozh" / "aktivnye.json").read_text()))

    def test_iz_budushchego_otklonyaetsya(self):
        baza, r = okruzhenie("ten_primery:iz_budushchego"); t = T.Ten("t1", baza, r)
        rez = t.prohod(now_ms=50 * H)
        self.assertEqual((rez["novyh"], rez["iz_budushchego"]), (0, 1))
        self.assertIn("ТРЕВОГА", (baza / "ten3_t1.log").read_text())

    def test_kill_v_reestre_ostanavlivaet(self):
        baza, r = okruzhenie(); t = T.Ten("t1", baza, r)
        r.verdikt_teni("G", "KILL", "SUDYA.json")
        self.assertTrue(t.prohod(now_ms=10 * H)["stop"])
        self.assertIn("остановлена", (baza / "ten3_t1.log").read_text())

    def test_odin_ekzemplyar(self):
        baza, r = okruzhenie(); t1 = T.Ten("t1", baza, r); t1.zamok()
        with self.assertRaises(T.OshibkaTeni): T.Ten("t1", baza, r).zamok()


if __name__ == "__main__":
    unittest.main()
