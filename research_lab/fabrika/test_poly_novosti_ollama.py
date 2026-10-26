import datetime as dt, json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import poly_novosti_ollama as P

S = dt.datetime(2026, 10, 26, 7, tzinfo=dt.timezone.utc)
EV = [{"tags": [{"slug": "geopolitics"}], "markets": [
    {"conditionId": "c1", "id": "m1", "question": "Will X sign a ceasefire by November 10?", "description": "Rules...", "active": True,
     "endDate": "2026-11-10T00:00:00Z", "volume": "90000", "outcomes": '["Yes","No"]', "outcomePrices": '["0.3","0.7"]', "clobTokenIds": '["t1","t2"]'},
    {"conditionId": "c2", "id": "m2", "question": "Will Bitcoin hit 100k?", "active": True, "endDate": "2026-11-10T00:00:00Z",
     "volume": "900000", "outcomes": '["Yes","No"]', "outcomePrices": '["0.3","0.7"]', "clobTokenIds": '["t3","t4"]'}]}]
RSS = b'<rss><channel><item><title>Talks advance</title><pubDate>Sun, 25 Oct 2026 10:00:00 GMT</pubDate></item><item><title>Future</title><pubDate>Tue, 27 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'


def gamma(url):
    if "/events?" in url: return EV if "offset=0" in url else []
    return {"closed": True, "outcomePrices": '["1","0"]'}


class T(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp()); P.D, P.ZH, P.SUD = d, d / "p.jsonl", d / "s.json"

    def test_otbor_bez_kripto_i_prognoz_odin_raz(self):
        kl = lambda s, z: {"p_yes": 0.6, "prichina": "x"}; kl.model = "fake"
        book = lambda t: {"bids": [{"price": "0.29"}], "asks": [{"price": "0.31"}]}
        r = P.prognoz(S, gamma, lambda u: RSS, book, kl)
        self.assertEqual(r["novyh_prognozov"], 1)
        z = json.loads(P.ZH.read_text().splitlines()[0])
        self.assertEqual(z["novostey"], 1)              # будущая новость отброшена
        self.assertEqual(z["fee"], 0.0); self.assertEqual(z["mid"], 0.3)
        self.assertEqual(P.prognoz(S, gamma, lambda u: RSS, book, kl)["novyh_prognozov"], 0)

    def test_sudya_malo(self):
        kl = lambda s, z: {"p_yes": 0.6}; kl.model = "fake"
        P.prognoz(S, gamma, lambda u: RSS, lambda t: {"bids": [{"price": "0.29"}], "asks": [{"price": "0.31"}]}, kl)
        r = P.sudya(gamma, dt.datetime(2026, 11, 11, tzinfo=dt.timezone.utc))
        self.assertEqual(r["razresheno"], 1); self.assertEqual(r["verdikt"], "INCONCLUSIVE_MALO")
        self.assertLess(r["brier"]["smes"], r["brier"]["rynok"])


if __name__ == "__main__":
    unittest.main()
