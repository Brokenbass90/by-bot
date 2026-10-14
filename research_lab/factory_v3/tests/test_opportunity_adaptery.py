import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import opportunity_adaptery as A, opportunity_v1 as O

H = 3_600_000


class TestLiq(unittest.TestCase):
    def test_sobytie_i_prichinnost(self):
        d = Path(tempfile.mkdtemp()); A.OPP = d; p = d / "v2.jsonl"; t0 = 1_790_000_000_000 // H * H
        rows = []
        for k in range(15 * 24):                                   # 15 суток фона: мелкие ликвидации
            rows.append(dict(schema="BYBIT_ALL_LIQUIDATION_SOURCE_V2", ts_ms=t0 + k * H + 5, symbol="XUSDT", side="long", usd=1000.0, recv_ts_ms=t0 + k * H + 100))
        hb = t0 + 15 * 24 * H
        rows.append(dict(schema="BYBIT_ALL_LIQUIDATION_SOURCE_V2", ts_ms=hb + 10, symbol="XUSDT", side="long", usd=90_000.0, recv_ts_ms=hb + 200))
        rows.append(dict(schema="BYBIT_ALL_LIQUIDATION_SOURCE_V2", ts_ms=hb + 20, symbol="XUSDT", side="short", usd=1_000.0, recv_ts_ms=hb + 300))
        rows.append(dict(schema="BYBIT_ALL_LIQUIDATION_SOURCE_V2", ts_ms=hb + H + 10, symbol="XUSDT", side="long", usd=90_000.0, recv_ts_ms=hb + 9 * H))  # поздняя
        p.write_text("\n".join(json.dumps(r) for r in rows))
        n, qa = A.liq_v2(p)
        self.assertEqual((n, qa["pozdnie"]), (1, 1))
        n2, _ = A.liq_v2(p, dyry=[(hb + 60_000, hb + 120_000)])            # дыра в час события → события нет
        self.assertEqual(n2, 0)
        p.write_text(p.read_text() + "\n" + json.dumps(dict(rows[-3], raw_item_canonical_sha256="a")) + "\n" + json.dumps(dict(rows[-3], raw_item_canonical_sha256="a")))
        self.assertEqual(A.liq_v2(p)[1]["dubli"], 1)
        z = O.prochitat(d / "LIQ_OTSKOK_4H_V2.csv.gz")[0]
        self.assertEqual(int(z["storona"]), 1); self.assertGreaterEqual(int(z["ts_resheniya_ms"]), hb + H)
        self.assertEqual(z["dohod_net_dolya"], "")                 # исхода нет — адаптер цены не читает


if __name__ == "__main__":
    unittest.main()
