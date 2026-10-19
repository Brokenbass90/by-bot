"""Тесты forward-тени трейлинга H6 (часть B). python3 -m unittest research_lab/fabrika/test_alpaca_treyl_ten.py"""
import datetime as dt, hashlib, json, sys, tempfile, unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB.parent)); sys.path.insert(0, str(LAB / "fabrika"))
import alpaca_treyl_ten as T  # noqa: E402
from research_lab.alpaca_h6_treyl import Ruka, vesti_poziciyu  # noqa: E402
from backtest.alpaca_exact_parity_contract import DailyBar  # noqa: E402


def _sessii(n, d0=dt.date(2026, 9, 1)):
    out, d = [], d0
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def _postavka(papka, put_cen, ses_n):
    ss = _sessii(ses_n)
    hist = {sym: [{"session": s.isoformat(), "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1}
                  for s, c in zip(ss, ceny)] for sym, ceny in put_cen.items()}
    d = {"session_date": ss[-1].isoformat(), "history": hist}
    f = papka / f"{ss[-1].isoformat()}.json"; f.write_text(json.dumps(d))
    (papka / f"{ss[-1].isoformat()}.delivery.json").write_text(
        json.dumps({"files": {f.name: hashlib.sha256(f.read_bytes()).hexdigest()}}))
    return ss


class Test(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        (self.t / "src").mkdir()
        T.SRC, T.H2B, T.ZH, T.SV = self.t / "src", self.t / "h2b.jsonl", self.t / "zh.jsonl", self.t / "sv.json"

    def _h2b(self, zz):
        T.H2B.write_text("".join(json.dumps(z) + "\n" for z in zz))

    def test_filtr_kogort_i_dopisyvanie(self):
        T.PERVAYA = "2026-09-25"
        b = {"AAA": {"top18": True, "setap": True, "ocenka": 2.0}, "BBB": {"top18": True, "setap": True, "ocenka": 3.0},
             "CCC": {"top18": False, "setap": True, "ocenka": 9.0}, "DDD": {"top18": True, "setap": False, "ocenka": None}}
        self._h2b([{"session": "2026-09-24", "klass": "FORWARD", "bumagi": b},
                   {"session": "2026-09-25", "klass": "BACKFILLED_DIAGNOSTIC", "bumagi": b},
                   {"session": "2026-09-28", "klass": "FORWARD", "entry_session": "2026-09-29", "bumagi": b}])
        n1 = T.kogorty_novye(); n2 = T.kogorty_novye()
        self.assertEqual([z["session"] for z in n1], ["2026-09-28"])
        self.assertEqual([p["sym"] for p in n1[0]["kogorta"]], ["BBB", "AAA"])
        self.assertEqual(n2, [])

    def test_vedenie_i_zavershenie(self):
        ss = _sessii(70)
        rost = [100 * (1.004 ** i) for i in range(70)]
        _postavka(T.SRC, {"AAA": rost, "BBB": rost}, 70)
        s, e = ss[30].isoformat(), ss[31].isoformat()
        T.PERVAYA = s
        b = {k: {"top18": True, "setap": True, "ocenka": 1.0} for k in ("AAA", "BBB")}
        self._h2b([{"session": s, "klass": "FORWARD", "entry_session": e, "bumagi": b}])
        r = T.prohod()
        self.assertEqual(r["zaversheno"], 1)
        sv = json.loads(T.SV.read_text())["bps"]["20"]["svodka"]
        self.assertEqual(sv["ruki"]["A35"]["raznica_s_A35_pp"], 0.0)
        self.assertIn("BEZ_TREYLA", sv["ruki"])

    def test_nezavershennaya(self):
        ss = _sessii(40)
        _postavka(T.SRC, {"AAA": [100.0] * 40}, 40)
        T.PERVAYA = ss[30].isoformat()
        self._h2b([{"session": ss[30].isoformat(), "klass": "FORWARD", "entry_session": ss[31].isoformat(),
                    "bumagi": {"AAA": {"top18": True, "setap": True, "ocenka": 1.0}}}])
        self.assertEqual(T.prohod()["zaversheno"], 0)

    def test_simulyator_stop_i_treyl(self):
        ss = _sessii(10)
        c = [100, 104, 106, 103, 101, 100, 100, 100, 100, 100]
        bars = [DailyBar(s, x, x, x, x) for s, x in zip(ss, c)]
        r = vesti_poziciyu(bars, 0, 100.0, 95.0, Ruka(3.5), 0.0)
        self.assertEqual(r["reason"], "gap_open")            # храповик от close 106 → 106·0.965, квантование вниз → 102.28; open 101 ниже
        self.assertAlmostEqual(r["stop"], 102.28, places=6)
        r2 = vesti_poziciyu(bars, 0, 100.0, 95.0, Ruka(1e12), 0.0)
        self.assertIsNone(r2["i_vyhod"])                       # без трейла стоп 95 не достигнут

    def test_nw_t(self):
        self.assertIsNone(T.nw_t([1.0, 1.0], 21))
        self.assertGreater(T.nw_t([1.0, 2.0, 1.5, 1.2, 1.8, 1.1], 2), 0)


if __name__ == "__main__":
    unittest.main()
