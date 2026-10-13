import datetime as dt, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fx_kontrakt_v1 as X

U = dt.timezone.utc
def t(*a): return dt.datetime(*a, tzinfo=U)


class TestFX(unittest.TestCase):
    def test_server_vremya_dst(self):
        # лето США: полночь сервера = 17:00 NY = 21:00 UTC; зима: 22:00 UTC
        self.assertEqual(X.server_v_utc(dt.datetime(2026, 7, 15, 0, 0)), t(2026, 7, 14, 21, 0))
        self.assertEqual(X.server_v_utc(dt.datetime(2026, 1, 15, 0, 0)), t(2026, 1, 14, 22, 0))
        # окно рассинхрона DST: США уже летнее (8.03), Европа ещё зимнее (до 29.03)
        self.assertEqual(X.server_v_utc(dt.datetime(2026, 3, 16, 0, 0)), t(2026, 3, 15, 21, 0))

    def test_rollovery_i_utroenie(self):
        ins = X.FIXTURES["EURUSD"]
        vh = dict(t=t(2026, 10, 13, 12), bid=1.10000, ask=1.10010)        # вторник
        vy = dict(t=t(2026, 10, 16, 12), bid=1.10000, ask=1.10010)        # пятница
        r = X.izderzhki_kruga_usd(ins, vh, vy, 1.0, +1)
        self.assertEqual(r["nochey"], 1 + 3 + 1)                           # вт→ср, ср→чт тройной, чт→пт
        self.assertAlmostEqual(r["spred_usd"], 10.0, 4)                    # (0.5+0.5 пипса)*10 пунктов*$1
        self.assertGreater(r["svop_usd"], 0)                               # лонг EUR платит своп (fixture)

    def test_vyhodnye_zakryty(self):
        self.assertFalse(X.rynok_otkryt(t(2026, 10, 17, 12)))              # суббота
        self.assertTrue(X.rynok_otkryt(t(2026, 10, 18, 22)))               # вс 18:00 NY — открыт
        self.assertFalse(X.rynok_otkryt(t(2026, 10, 16, 21, 30)))          # пт 17:30 NY — закрыт
        with self.assertRaises(X.OshibkaFX):
            X.izderzhki_kruga_usd(X.FIXTURES["EURUSD"], dict(t=t(2026, 10, 17, 12), bid=1.1, ask=1.1001),
                                  dict(t=t(2026, 10, 19, 12), bid=1.1, ask=1.1001), 1.0, 1)

    def test_usdjpy_stoimost_punkta(self):
        self.assertAlmostEqual(X.stoimost_punkta_usd(X.FIXTURES["USDJPY"], 150.0), 100_000 * 0.001 / 150.0, 9)
        self.assertAlmostEqual(X.stoimost_punkta_usd(X.FIXTURES["XAUUSD"], 2400.0), 1.0, 9)

    def test_boevoy_rezhim_otkazyvaet_fixtures(self):
        with self.assertRaises(X.OshibkaFX):
            X.izderzhki_kruga_usd(X.FIXTURES["XAUUSD"], dict(t=t(2026, 10, 13, 12), bid=2400, ask=2400.3),
                                  dict(t=t(2026, 10, 13, 15), bid=2401, ask=2401.3), 0.01, 1, boevoy=True)

    def test_lot_i_kotirovka(self):
        ins = X.FIXTURES["EURUSD"]; q = dict(t=t(2026, 10, 13, 12), bid=1.1, ask=1.1001)
        with self.assertRaises(X.OshibkaFX): X.izderzhki_kruga_usd(ins, q, q, 0.015, 1)
        with self.assertRaises(X.OshibkaFX): X.izderzhki_kruga_usd(ins, dict(q, ask=1.0999), q, 0.01, 1)

    def test_sessii_dst(self):
        self.assertEqual(X.sessiya(t(2026, 7, 15, 13)), "OVERLAP")         # 14:00 Лондон, 09:00 NY
        self.assertEqual(X.sessiya(t(2026, 7, 15, 2)), "ASIA")
        self.assertEqual(X.sessiya(t(2026, 10, 17, 12)), "CLOSED")

    def test_proverka_kotirovok(self):
        rows = [(t(2026, 10, 13, 12), 1.1, 1.1001), (t(2026, 10, 13, 12), 1.1, 1.1001),
                (t(2026, 10, 13, 13), 1.1002, 1.1), (t(2026, 10, 17, 12), 1.1, 1.1001)]
        r = X.proverit_kotirovki(rows, X.FIXTURES["EURUSD"])
        self.assertEqual((r["nazad"], r["perekreshcheno"], r["v_zakrytom_rynke"]), (1, 1, 1))
        self.assertEqual(r["dyr_v_sessii"], 1)                              # 12:00→13:00 вт, рынок открыт


if __name__ == "__main__":
    unittest.main()
