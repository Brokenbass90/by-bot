import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reestr_v1 import Reestr
import ferma_v1 as F


def novyy_reestr():
    r = Reestr(Path(tempfile.mkdtemp()) / "r.jsonl")
    r.semya("SH", "шум"); r.gipoteza("G", "SH", "моментум на шуме", ["sintetika"]); r.perehod("G", "SCREEN", "старт")
    r.okno("DEV", "sintetika", "2021-01-01", "2023-12-31", "DEV", byudzhet=500)
    r.okno("CONF", "sintetika", "2024-01-01", "2024-12-31", "CONFIRM", byudzhet=5)
    r.okno("HOLD", "sintetika", "2026-01-01", "2026-12-31", "HOLDOUT")
    r.okno("BAD", "sintetika", "2025-06-01", "2026-03-01", "DEV", byudzhet=5)    # залезает в HOLDOUT
    return r


def spec(i, okno="DEV", eks="ferma_primery:moment_na_shume", **p):
    return dict(id=f"E{i}", gipoteza="G", okno=okno, eksperiment=eks, parametry=dict(dict(sym=f"S{i % 12}", lookback=5 + i % 40, hold=1 + i % 7), **p),
                kriterii=dict(min_n=30, znak="+"))


class TestFerma(unittest.TestCase):
    def test_shum_ne_prohodit_s_popravkoy(self):
        r = novyy_reestr()
        it = F.zapustit([spec(i) for i in range(60)], r, processov=4)
        pas = [x for x in it if x["status"] == "PASS"]
        bez_popravki = [x for x in it if x.get("t", 0) >= 1.96]
        self.assertEqual(len(pas), 0, f"ложные находки на шуме: {pas}")
        self.assertEqual(len(it), 60)
        print(f"\n  шум: без поправки t≥1.96 у {len(bez_popravki)} из 60; с поправкой PASS 0 (порог {it[-1]['trebuemyy_t']})")

    def test_zabor_okna(self):
        r = novyy_reestr()
        it = F.zapustit([dict(spec(1), eksperiment="ferma_primery:podglyadyvaet")], r, processov=1)
        m = r.sostoyanie()["popytki"]["E1"]["rezultat"]["metrika"]
        self.assertGreaterEqual(m["t_min"], F.ms("2021-01-01")); self.assertLessEqual(m["t_max"], F.ms("2023-12-31") + 86_400_000)

    def test_holdout_i_confirm_nedostupny(self):
        r = novyy_reestr()
        it = F.zapustit([spec(1, okno="HOLD"), spec(2, okno="CONF")], r, processov=1)
        self.assertTrue(all(x["status"] == "OTKAZ_REESTRA" for x in it))
        it = F.zapustit([dict(spec(3, okno="BAD"), eksperiment="ferma_primery:podglyadyvaet")], r, processov=1)
        self.assertEqual(it[0]["status"], "OSHIBKA_EKSPERIMENTA"); self.assertIn("HOLDOUT", it[0]["prichina"])

    def test_povtor_id_otkaz(self):
        r = novyy_reestr()
        F.zapustit([spec(1)], r, processov=1)
        self.assertEqual(F.zapustit([spec(1)], r, processov=1)[0]["status"], "OTKAZ_REESTRA")


if __name__ == "__main__":
    unittest.main()
