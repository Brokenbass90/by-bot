"""Тесты продолжения дневок Binance. python3 -m unittest research_lab/fabrika/test_binance_d1_vpered.py"""
import datetime as dt, json, sys, tempfile, unittest, urllib.error
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import binance_d1_vpered as B  # noqa: E402

D = B.DEN_MS
T0 = 1790726400000  # 2026-09-30


def fake(days_after=25, bez_spota=("ZZZUSDT",)):
    def get(url):
        sym = url.split("symbol=")[1].split("&")[0]; start = int(url.split("startTime=")[1].split("&")[0])
        if "api.binance.com" in url and sym in bez_spota:
            raise urllib.error.HTTPError(url, 400, "bad", None, None)
        rows = []
        t = start
        while t <= T0 + days_after * D and len(rows) < 100:
            rows.append([t, "1", "2", "0.5", "1.5", "10", t + D - 1, "100", 5, "4", "60", "0"]); t += D
        return rows
    return get


class Test(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        B.ARH, B.OUT, B.ZH, B.SOST = d / "arh", d / "out", d / "zh.jsonl", d / "out" / "sost.json"
        for vid in ("taker", "spot_taker", "klines"):
            (B.ARH / vid).mkdir(parents=True)
            for s in ("BTCUSDT", "ZZZUSDT"):
                row = [T0, 100.0, 60.0] if vid != "klines" else [T0, 1, 2, 0.5, 1.5, 10]
                (B.ARH / vid / f"{s}.json").write_text(json.dumps([row]))
        self.arh_do = {p: p.read_text() for p in B.ARH.rglob("*.json")}

    def test_dopisyvaet_tolko_zakrytye_i_ne_trogaet_arhiv(self):
        now = dt.datetime(2026, 10, 20, 6, 0, tzinfo=dt.timezone.utc)
        r = B.prohod(now, get=fake(), pauza=0)
        self.assertEqual(r["parnost"], "PASS")
        v = json.loads((B.OUT / "taker" / "BTCUSDT.json").read_text())
        self.assertEqual(v[0][0], T0 + D)
        self.assertEqual(dt.datetime.fromtimestamp(v[-1][0] / 1000, dt.timezone.utc).date(), dt.date(2026, 10, 19))
        self.assertEqual(len(json.loads((B.OUT / "klines" / "BTCUSDT.json").read_text())), len(v))
        self.assertEqual({p: p.read_text() for p in B.ARH.rglob("*.json")}, self.arh_do)
        r2 = B.prohod(now, get=fake(), pauza=0)          # повтор того же дня — ничего нового
        self.assertEqual(r2["dopisano_dney"], 0)

    def test_net_spota_pomechaetsya(self):
        now = dt.datetime(2026, 10, 20, 6, 0, tzinfo=dt.timezone.utc)
        B.prohod(now, get=fake(), pauza=0)
        s = json.loads(B.SOST.read_text())
        self.assertIn("spot:ZZZUSDT", s["net_na_binance"])
        self.assertFalse((B.OUT / "spot_taker" / "ZZZUSDT.json").exists())

    def test_parnost_fail(self):
        def plohoy(url):
            r = fake()(url); r[0][7] = "101"; return r
        self.assertEqual(B.parnost(plohoy, simv=("BTCUSDT",))["status"], "FAIL")

    def test_bez_seti_unknown_i_povtor(self):
        def net(url): raise OSError("no network")
        now = dt.datetime(2026, 10, 20, 6, 0, tzinfo=dt.timezone.utc)
        r = B.prohod(now, get=net, pauza=0)
        self.assertEqual(r["parnost"], "UNKNOWN"); self.assertGreater(r["oshibok"], 0)
        self.assertEqual(B.prohod(now, get=fake(), pauza=0)["parnost"], "PASS")


if __name__ == "__main__":
    unittest.main()
