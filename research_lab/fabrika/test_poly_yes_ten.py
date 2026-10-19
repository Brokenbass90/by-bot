"""Тесты тени poly_yes_ten без сети: окно решения, NO-ask как цена входа, ликвидность, исход по разрешению Polymarket."""
import datetime as dt, sys, unittest
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parent))
import poly_yes_ten as P
NY = ZoneInfo("America/New_York")
R = int(dt.datetime(2026, 10, 25, 12, 0, tzinfo=NY).timestamp() * 1000); T = R - 86400_000


def snimok(bid=0.90, ask=0.92, t=None):
    return {"c1": {"t": t or T - 5 * 60_000, "conditionId": "c1", "vopros": "Will the price of Bitcoin be above $110,000 on October 25?",
                   "bids": [[bid, 100.0]], "asks": [[ask, 100.0]]}}


class T_(unittest.TestCase):
    def test_vhod_po_ask_no(self):
        r = P.resheniya(set(), snimok(), T, stakan_fn=lambda c: (dict(no_token="n", ask_no=0.11, razmer_ask=500.0, uroven_ask=3), None))
        self.assertEqual(r[0]["status"], "VHOD"); self.assertEqual(r[0]["cena_no"], 0.11); self.assertEqual(r[0]["zerkalo_no"], 0.1)

    def test_vne_okna_i_diapazona(self):
        self.assertEqual(P.resheniya(set(), snimok(), T + 2 * 3600_000, stakan_fn=None), [])
        r = P.resheniya(set(), snimok(0.97, 0.98), T, stakan_fn=None); self.assertEqual(r[0]["status"], "VNE_DIAPAZONA")

    def test_likvidnost_i_set(self):
        r = P.resheniya(set(), snimok(), T, stakan_fn=lambda c: (dict(no_token="n", ask_no=0.11, razmer_ask=5.0, uroven_ask=1), None))
        self.assertEqual(r[0]["status"], "NO_LIQUIDITY")
        def boom(c): raise OSError("net")
        self.assertTrue(P.resheniya(set(), snimok(), T, stakan_fn=boom)[0]["status"].startswith("NET_STAKANA"))

    def test_do_zamorozki_ne_reshenie(self):
        self.assertEqual(P.resheniya(set(), snimok(t=P.ZAMOROZKA_MS - 1), T, stakan_fn=None), [])

    def test_ishod_po_razresheniyu(self):
        z = dict(tip="reshenie", conditionId="c1", status="VHOD", cena_no=0.10, raschet_ms=R, aktiv="Bitcoin", X=110000.0)
        g = lambda c: {"closed": True, "outcomes": '["Yes","No"]', "outcomePrices": '["0","1"]'}
        o = P.ishody([z], R + 3600_000, gamma_fn=g)[0]
        self.assertTrue(o["no_vyigral"]); self.assertAlmostEqual(o["dohod"], 9.0)
        g2 = lambda c: {"closed": False}
        self.assertEqual(P.ishody([z], R + 3600_000, gamma_fn=g2), [])


if __name__ == "__main__":
    unittest.main()
