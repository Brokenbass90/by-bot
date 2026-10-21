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
        r = P.resheniya(set(), snimok(), T, stakan_fn=lambda c, **k: (dict(no_token="n", vwap_no_10usd=0.11, tokenov_na_10usd=10 / 0.11, gamma_indikativno={}), None))
        self.assertEqual(r[0]["status"], "VHOD"); self.assertEqual(r[0]["zerkalo_no_tolko_sravnenie"], 0.1)
        self.assertAlmostEqual(r[0]["cena_no"], 0.11 + 0.07 * 0.11 * 0.89, places=6)          # комиссия Polymarket по формуле
        self.assertAlmostEqual(r[0]["cena_no_stress"], 0.11 + 0.10 * 0.11 * 0.89 + 0.01, places=6)
        b = r[0]["byudzhet"]; self.assertAlmostEqual(b["tokeny_usd"], 10.0, places=3)
        self.assertAlmostEqual(b["vsego_usd"], 10.0 + b["komissiya_usd"], places=3)              # комиссия сверху и учтена в доходе

    def test_vne_okna_i_diapazona(self):
        self.assertEqual(P.resheniya(set(), snimok(), T + 2 * 3600_000, stakan_fn=None), [])
        r = P.resheniya(set(), snimok(0.97, 0.98), T, stakan_fn=None); self.assertEqual(r[0]["status"], "VNE_DIAPAZONA")

    def test_likvidnost_i_set(self):
        r = P.resheniya(set(), snimok(), T, stakan_fn=lambda c, **k: (None, "NO_LIQUIDITY"))
        self.assertEqual(r[0]["status"], "NO_LIQUIDITY")
        def boom(c, **k): raise OSError("net")
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


class TestStakan(unittest.TestCase):
    """PM 19.10: минимальный ask независимо от порядка, доллары = цена × токены, VWAP на 10 $, пропуски без подмены 1 − YES."""
    def kniga(self, asks, bids=(), ts=None, asset="n", market="c1", mos="5"):
        return {"asks": [{"price": str(p), "size": str(s)} for p, s in asks], "bids": [{"price": str(p), "size": str(s)} for p, s in bids],
                "timestamp": str(ts if ts is not None else T), "asset_id": asset, "market": market, "min_order_size": mos}

    def test_poryadok_i_dollary(self):
        st, e = P.razobrat_stakan_no(self.kniga([(0.20, 1000), (0.11, 50), (0.15, 500)]), "n", "c1", T)
        self.assertIsNone(e); self.assertEqual(st["best_ask_no"], 0.11); self.assertAlmostEqual(st["razmer_best_ask_usd"], 5.5)
        # 50 токенов × 0.11 = 5.5 $ не хватает → добираем на 0.15: VWAP = 10 / (50 + 4.5/0.15)
        self.assertAlmostEqual(st["vwap_no_10usd"], round(10 / (50 + 4.5 / 0.15), 6))

    def test_malo_glubiny(self):
        self.assertEqual(P.razobrat_stakan_no(self.kniga([(0.001, 5000)]), "n", "c1", T)[1], "NO_LIQUIDITY")   # 5 $ всего

    def test_propuski(self):
        k = lambda **kw: P.razobrat_stakan_no(self.kniga([(0.11, 1000)], **{x: v for x, v in kw.items() if x != "bid_yes"}), "n", "c1", T,
                                              kw.get("bid_yes"))[1]
        self.assertEqual(k(ts=T - 10 * 60_000), "STAKAN_USTAREL")
        self.assertEqual(k(asset="drugoy"), "TOKEN_NE_SOVPAL")
        self.assertEqual(k(market="c2"), "RYNOK_NE_SOVPAL")
        self.assertEqual(k(bid_yes=0.70), "PROTIVORECHIE_YES_NO")
        self.assertEqual(P.razobrat_stakan_no(self.kniga([(0.11, 1000)], bids=[(0.12, 10)]), "n", "c1", T)[1], "STAKAN_PERESECHEN")
        self.assertEqual(P.razobrat_stakan_no(self.kniga([]), "n", "c1", T)[1], "NO_LIQUIDITY")

    def test_min_order(self):
        self.assertEqual(P.razobrat_stakan_no(self.kniga([(0.90, 1000)], mos="50"), "n", "c1", T)[1], "MENSHE_MIN_ORDERA")



class TestGammaZakrytye(unittest.TestCase):
    def test_zakrytyy_rynok_ishchetsya_s_closed_true(self):
        vyzovy = []
        def fake(base, path, **q):
            vyzovy.append(q)
            return [{"closed": True, "conditionId": q["condition_ids"]}] if q.get("closed") == "true" else []
        m = P.rynok_gamma("0xabc", get_fn=fake)
        self.assertTrue(m["closed"]); self.assertEqual(len(vyzovy), 2)


if __name__ == "__main__":
    unittest.main()
