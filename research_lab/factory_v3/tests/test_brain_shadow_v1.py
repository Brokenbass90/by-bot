import json, sys, tempfile, unittest
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(HERE))
import opportunity_v2 as V2, brain_shadow_v1 as B, brain_metriki as M   # noqa: E402

H = 3_600_000


def opp(sym="AUSDT", side=1, t=10 * H, sleeve="KITY_BYBIT", status="HIST_DEV_PASS", **kw):
    a = dict(source_ref="x", source_sha256="a" * 64, t_observation_ms=t - H, t_available_ms=t, t_decision_ms=t, sleeve=sleeve,
             mechanism="M", version="v", symbol=sym, side=side, horizon_ms=8 * 24 * H, context={}, features={}, exp_gross_bps=44.0,
             cost_fee_bps=12.0, cost_spread_bps=3.0, cost_slip_bps=3.0, cost_funding_bps=0.0, uncertainty_bps=25.0,
             prior_ref="p", prior_status=status); a.update(kw); return V2.vozmozhnost(**a)


class T(unittest.TestCase):
    def test_prichinnost_i_unknown(self):
        with self.assertRaises(V2.OshibkaV2): opp(t_observation_ms=11 * H)
        self.assertEqual(opp(cost_funding_bps=V2.UNKNOWN)["exp_net_bps"], V2.UNKNOWN)
        with self.assertRaises(V2.OshibkaV2): opp(cost_fee_bps=None)
        with self.assertRaises(V2.OshibkaV2): opp(exp_gross_bps=True)
        self.assertEqual(opp()["exp_net_bps"], 26.0)

    def test_cepochka_dubl_ishod(self):
        with tempfile.TemporaryDirectory() as d:
            hr = V2.Hranilishche(d); v = opp()
            self.assertIsNotNone(hr.dobavit_vozmozhnost(v, 10 * H)); self.assertIsNone(hr.dobavit_vozmozhnost(v, 10 * H))
            hr.dobavit_reshenie(v["opp_id"], "BASELINE_V1", "s", 1.0, [], 10 * H)
            hr.prikrepit_ishod(v["opp_id"], 20 * H, 15.0, "y", "b" * 64, 20 * H)
            self.assertIsNone(hr.prikrepit_ishod(v["opp_id"], 20 * H, 15.0, "y", "b" * 64))
            with self.assertRaises(V2.OshibkaV2): hr.prikrepit_ishod(v["opp_id"], 20 * H, 16.0, "y", "b" * 64)
            with self.assertRaises(V2.OshibkaV2): hr.dobavit_reshenie(v["opp_id"], "BRAIN_V1", "s", 1.0, [])
            V2.Hranilishche(d)                                                  # цепочка читается
            p = Path(d) / "decisions.jsonl"; s = p.read_text().replace('"allocation_units": 1.0', '"allocation_units": 2.0'); p.write_text(s)
            with self.assertRaises(V2.OshibkaV2): V2.Hranilishche(d)

    def test_late(self):
        with tempfile.TemporaryDirectory() as d:
            hr = V2.Hranilishche(d); z = hr.dobavit_vozmozhnost(opp(), 10 * H + V2.LAG_MS + 1); self.assertTrue(z["late"])

    def test_politiki_i_risk(self):
        v = opp(); self.assertEqual(B.baseline_v1(v, [])[0], 1.0)
        u, ogr = B.brain_v1(v, []); self.assertAlmostEqual(u, (26 - 12.5) / 20)
        self.assertEqual(B.brain_v1(opp(status="HIST_DEV_KILL"), [])[0], 0.0)
        otkr = [(opp(sym="AUSDT", t=9 * H), 1.0)]
        self.assertEqual(B.risk_engine(v, 1.0, otkr), (0.0, ["cap_symbol"]))
        otkr = [(opp(sym=f"S{i}", t=9 * H), 1.0) for i in range(6)]
        self.assertEqual(B.risk_engine(opp(sym="ZUSDT"), 1.0, otkr)[0], 0.0)           # кластер (рукав, сторона) = 6
        self.assertEqual(B.risk_engine(opp(sym="ZUSDT", side=-1), 1.0, otkr)[0], 1.0)

    def test_kontekst_tolko_proshloe(self):
        bary = [[i * H, 100, 101, 99, 100 + i * 0.01, 1] for i in range(600)]
        c = B.kontekst(500 * H, bary); self.assertEqual(c["bar_ts"], 499 * H); self.assertEqual(c["rezhim_v1"], V2.UNKNOWN)
        c2 = B.kontekst_fabrika(bary)(500 * H); self.assertEqual(c2["bar_ts"], 499 * H); self.assertIn(c2["rezhim_v1"], ("BULL_TREND", "BEAR_TREND", "NEUTRAL"))
        self.assertEqual(B.kontekst(500 * H, None)["btc_rezhim"], V2.UNKNOWN)

    def test_metriki(self):
        m = M.metriki([10, -20, 5, 5, 15]); self.assertEqual(m["maxdd"], 20); self.assertEqual(m["recovery_dney_max"], 3)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(M.sravnit(d)["status"], "NEDOSTATOCHNO")


if __name__ == "__main__":
    unittest.main()
