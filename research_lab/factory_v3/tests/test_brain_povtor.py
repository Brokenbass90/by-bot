import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import brain_povtor as P

H = 3_600_000


def opp(i, t, sleeve="KITY_BYBIT", sym="AAAUSDT", side=1, **kw):
    z = dict(opp_id=f"o{i}", t_decision_ms=t, t_available_ms=t, t_observation_ms=t, late=False, horizon_ms=10 * H,
             sleeve=sleeve, symbol=sym, side=side, mechanism="X", prior_status="HIST_DEV_PASS", exp_net_bps=60.0,
             uncertainty_bps=20.0, cost_fee_bps=12.0, cost_spread_bps=3.0, cost_slip_bps=3.0, cost_funding_bps=0.0,
             context={"rezhim_v1": "UNKNOWN"}, features={})
    z.update(kw); return z


class TestPovtor(unittest.TestCase):
    T0 = P.T0_MS

    def test_do_t0_ne_vliyaet(self):
        a = [opp(1, self.T0 - H), opp(2, self.T0 + H)]
        b = [opp(2, self.T0 + H)]
        self.assertEqual(P.povtor(a), P.povtor(b))               # унаследованные позиции не занимают риск ни у кого

    def test_determinizm_i_poryadok(self):
        z = [opp(i, self.T0 + i * H, sym=f"S{i}USDT") for i in range(5)]
        self.assertEqual(P.povtor(z), P.povtor(list(reversed(z))))

    def test_odin_potok_dlya_vseh(self):
        r = P.povtor([opp(i, self.T0 + i, sym=f"S{i}USDT") for i in range(3)])
        ids = {p: [x[0] for x in d] for p, d in r.items()}
        self.assertEqual(len({tuple(v) for v in ids.values()}), 1)

    def test_ishody_ne_chitayutsya(self):
        a = opp(1, self.T0 + H); b = dict(a, R_bps=999.0, ishod={"x": 1}, record_hash="zz")
        self.assertEqual(P.povtor([a]), P.povtor([b]))

    def test_risk_obshchiy(self):
        z = [opp(i, self.T0 + i, sym="SAMEUSDT") for i in range(3)]
        r = P.povtor(z, politiki={"BASELINE_V1": P.B.POLITIKI["BASELINE_V1"]})
        self.assertEqual([u for _, u, _ in r["BASELINE_V1"]], [1.0, 0.0, 0.0])   # symbol cap 1


if __name__ == "__main__":
    unittest.main()
