import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reestr_v1 import Reestr, OshibkaReestra, trebuemyy_t

SPEC = {"priznak": "x", "porog": 1}
KR = {"min_n": 20, "znak": "+"}


class TestReestr(unittest.TestCase):
    def setUp(self):
        self.r = Reestr(Path(tempfile.mkdtemp()) / "r.jsonl")
        self.r.semya("S1", "поток агрессора спот недельный")
        self.r.gipoteza("G1", "S1", "спот-доля агрессора", ["binance_spot"])
        self.r.okno("DEV1", "binance", "2023-01-01", "2024-12-31", "DEV", byudzhet=3)
        self.r.okno("CONF1", "binance", "2025-01-01", "2025-12-31", "CONFIRM", byudzhet=5)
        self.r.okno("HOLD", "binance", "2026-01-01", "2026-12-31", "HOLDOUT")

    def test_porog_rastet_s_perebor(self):
        self.assertAlmostEqual(trebuemyy_t(1), 1.96, 2)
        self.assertGreater(trebuemyy_t(100), 3.4)
        self.assertGreater(trebuemyy_t(1000), trebuemyy_t(100))

    def test_nelzya_popytku_v_new(self):
        with self.assertRaises(OshibkaReestra):
            self.r.zaregistrirovat_popytku("P1", "G1", "DEV1", "SCREEN", SPEC, KR)   # гипотеза ещё NEW

    def test_polnyy_put_i_vorota(self):
        r = self.r
        r.perehod("G1", "SCREEN", "старт")
        r.zaregistrirovat_popytku("P1", "G1", "DEV1", "SCREEN", SPEC, KR)
        with self.assertRaises(OshibkaReestra):
            r.perehod("G1", "TEST", "рано")                                     # нет PASS скрининга
        rez = r.zapisat_rezultat("P1", SPEC, t=2.5, n=50)
        self.assertEqual(rez["verdikt"], "PASS")
        r.perehod("G1", "TEST", "скрининг PASS")
        with self.assertRaises(OshibkaReestra):
            r.zaregistrirovat_popytku("P2", "G1", "DEV1", "TEST", SPEC, KR)     # DEV-окно не для TEST
        r.zaregistrirovat_popytku("P2", "G1", "CONF1", "TEST", SPEC, KR)
        with self.assertRaises(OshibkaReestra):
            r.zaregistrirovat_popytku("P3", "G1", "CONF1", "TEST", SPEC, KR)    # одна попытка на CONFIRM
        r.zapisat_rezultat("P2", SPEC, t=3.0, n=60)
        r.perehod("G1", "SHADOW", "TEST PASS")
        with self.assertRaises(OshibkaReestra):
            r.perehod("G1", "CANARY", "без GO")
        r.perehod("G1", "CANARY", "тень ок", owner_go="Николай: GO 2026-10-20")
        self.assertEqual(r.sostoyanie()["gipotezy"]["G1"]["status"], "CANARY")

    def test_holdout_zapreshchen(self):
        self.r.perehod("G1", "SCREEN", "старт")
        with self.assertRaises(OshibkaReestra):
            self.r.zaregistrirovat_popytku("P1", "G1", "HOLD", "SCREEN", SPEC, KR)

    def test_byudzhet_okna(self):
        r = self.r; r.perehod("G1", "SCREEN", "старт")
        for i in range(3):
            r.zaregistrirovat_popytku(f"P{i}", "G1", "DEV1", "SCREEN", dict(SPEC, i=i), KR)
        with self.assertRaises(OshibkaReestra):
            r.zaregistrirovat_popytku("P9", "G1", "DEV1", "SCREEN", SPEC, KR)

    def test_popravka_menyaet_verdikt(self):
        r = self.r; r.perehod("G1", "SCREEN", "старт")
        for i in range(3):
            r.zaregistrirovat_popytku(f"P{i}", "G1", "DEV1", "SCREEN", dict(SPEC, i=i), KR)
        rez = r.zapisat_rezultat("P0", dict(SPEC, i=0), t=2.1, n=50)           # 2.1 ≥ 1.96, но < t(k=3)=2.39
        self.assertEqual(rez["verdikt"], "FAIL")

    def test_spec_nelzya_menyat_i_povtor(self):
        r = self.r; r.perehod("G1", "SCREEN", "старт")
        r.zaregistrirovat_popytku("P1", "G1", "DEV1", "SCREEN", SPEC, KR)
        with self.assertRaises(OshibkaReestra):
            r.zapisat_rezultat("P1", dict(SPEC, porog=2), t=3, n=50)
        r.zapisat_rezultat("P1", SPEC, t=3, n=50)
        with self.assertRaises(OshibkaReestra):
            r.zapisat_rezultat("P1", SPEC, t=5, n=50)

    def test_kriterii_obyazatelny_i_min_n(self):
        r = self.r; r.perehod("G1", "SCREEN", "старт")
        with self.assertRaises(OshibkaReestra):
            r.zaregistrirovat_popytku("P1", "G1", "DEV1", "SCREEN", SPEC, {})
        r.zaregistrirovat_popytku("P1", "G1", "DEV1", "SCREEN", SPEC, KR)
        self.assertEqual(r.zapisat_rezultat("P1", SPEC, t=9, n=5)["verdikt"], "FAIL")

    def test_kill_terminalen_i_kladbische(self):
        r = self.r
        r.perehod("G1", "KILL", "FAIL")
        with self.assertRaises(OshibkaReestra):
            r.perehod("G1", "SCREEN", "воскресить")
        r.zakryt_semyu("S1", "G6 исчерпан")
        with self.assertRaises(OshibkaReestra):
            r.gipoteza("G2", "S1", "ещё вариант", [])
        self.assertTrue(r.pohozhie("недельный поток агрессора на споте"))

    def test_budushchee_okno_rezultat_tolko_posle_konca(self):
        r = self.r; r.okno("FWD", "binance", "2026-10-13", "2099-12-31", "CONFIRM", byudzhet=5)
        r.perehod("G1", "SCREEN", "старт"); r.zaregistrirovat_popytku("P1", "G1", "DEV1", "SCREEN", SPEC, KR)
        r.zapisat_rezultat("P1", SPEC, t=3, n=50); r.perehod("G1", "TEST", "ok")
        r.zaregistrirovat_popytku("PF", "G1", "FWD", "TEST", SPEC, KR)          # регистрация ДО данных — можно
        with self.assertRaises(OshibkaReestra):
            r.zapisat_rezultat("PF", SPEC, t=3, n=50)                           # результат до конца окна — нельзя

    def test_nasledie(self):
        r = self.r
        with self.assertRaises(OshibkaReestra):
            r.nasledie("G1", "SHADOW", "")
        r.nasledie("G1", "SHADOW", "PREREG_X.md")
        self.assertEqual(r.sostoyanie()["gipotezy"]["G1"]["status"], "SHADOW")
        with self.assertRaises(OshibkaReestra):
            r.nasledie("G1", "MONEY", "PREREG_X.md")                            # только один раз

    def test_zhurnal_append_only(self):
        n0 = len(self.r.put.read_text().splitlines())
        self.r.perehod("G1", "SCREEN", "старт")
        self.assertEqual(len(self.r.put.read_text().splitlines()), n0 + 1)


if __name__ == "__main__":
    unittest.main()
