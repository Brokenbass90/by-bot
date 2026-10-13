import copy, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reestr_v1 import Reestr
import ai_kontrakt_v1 as A

HOROSHEE = dict(
    id="UNLOCK_PRESSURE_PERP", semya="RAZLOK_PREDLOZHENIE",
    mehanizm="Держатели токенов с вестингом получают разлок и вынуждены продавать часть; маркет-мейкеры заранее шортят перп, "
             "перп дешевеет относительно спота за дни до события.",
    pochemu_ne_arbitrazhirovano="ёмкость мала на альтах, календарь разлоков платный и разрозненный",
    istochniki_dannyh=["binance_klines_d1", "bybit_funding"], priznak="базис перп/спот за 5 дней до события",
    vremya_izvestnosti="закрытие дня d−1", napravlenie="-", gorizont="1w", vselennaya="PIT топ-100",
    kontrol="случайные даты той же монеты", falsifikaciya="избыток над контролем ≤ 0 в обеих половинах",
    ozhidaemaya_chastota_v_mesyac=12, izderzhki_ocenka_bps=20)


class Fake:
    def __init__(self, otvety): self.otvety = list(otvety); self.model = "fake"; self.sistema = None
    def __call__(self, sistema, zapros):
        self.sistema = sistema; x = self.otvety.pop(0)
        if isinstance(x, Exception): raise x
        return x


class TestAIKontrakt(unittest.TestCase):
    def setUp(self):
        self.r = Reestr(Path(tempfile.mkdtemp()) / "r.jsonl")
        self.r.semya("SPOT_POTOK", "доля агрессора на споте Binance недельная кросс-секция", status="KILL")

    def test_horoshee_prohodit_v_new(self):
        self.assertEqual(A.proverit(HOROSHEE), [])
        rez = A.predlozhit(HOROSHEE, self.r, "fake")
        self.assertEqual(rez["status"], "NEW")
        self.assertEqual(self.r.sostoyanie()["gipotezy"]["AI_UNLOCK_PRESSURE_PERP"]["status"], "NEW")

    def test_zapreshchennye_polya(self):
        for k in ("porog_t", "kriterii", "risk_mult", "plecho", "live_orders", "status", "okno_confirm"):
            x = copy.deepcopy(HOROSHEE); x[k] = 1
            self.assertTrue(any("запрещённое" in e for e in A.proverit(x)), k)
        x = copy.deepcopy(HOROSHEE); x["kontrol"] = {"sudya": "мой"}
        self.assertTrue(any("запрещённое" in e for e in A.proverit(x)))

    def test_istochnik_vne_kataloga_i_pustoy_mehanizm(self):
        x = dict(HOROSHEE, istochniki_dannyh=["twitter_firehose"], mehanizm="растёт")
        err = A.proverit(x)
        self.assertTrue(any("каталога" in e for e in err)); self.assertTrue(any("короткий" in e for e in err))

    def test_kladbische(self):
        x = dict(HOROSHEE, id="SPOT_AGRESSOR", semya="SPOT_POTOK",
                 mehanizm="Доля агрессора на споте Binance показывает настоящий спрос без плеча, недельная кросс-секция монет топ-50.")
        self.assertTrue(A.predlozhit(x, self.r)["status"].startswith("OTKLONENO_DUBL"))

    def test_raund_ne_padaet_na_oshibkah_modeli(self):
        k = Fake([RuntimeError("timeout"), {"id": "x"}, HOROSHEE])
        rez = A.raund(self.r, k, n=3)
        self.assertEqual([x["status"] for x in rez], ["OSHIBKA_MODELI", "OTKLONENO_KONTRAKT", "NEW"])
        self.assertIn("SPOT_POTOK", k.sistema)                                   # кладбище подаётся в промпт

    def test_ii_ne_mozhet_menyat_status(self):
        A.predlozhit(HOROSHEE, self.r)
        st = self.r.sostoyanie()["gipotezy"]["AI_UNLOCK_PRESSURE_PERP"]
        self.assertEqual(st["status"], "NEW"); self.assertEqual(st["istoriya"], [])


if __name__ == "__main__":
    unittest.main()
