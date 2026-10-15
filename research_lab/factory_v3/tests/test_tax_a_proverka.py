import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tax_a_proverka as T

FILL = dict(kind="fill", venue="bybit", account_type="UTA", t_ms=1792080000000, ccy="USDT", source_ref="x#1", source_sha256="a" * 64,
            order_id="o1", trade_id="t1", instrument="BTCUSDT", instrument_type="perp", side="buy", qty=0.001, px=60000, fee=0.03,
            fee_ccy="USDT", liquidity="maker")


class T1(unittest.TestCase):
    def zap(self, stroki):
        p = Path(tempfile.mkdtemp()) / "e.jsonl"; p.write_text("\n".join(json.dumps(z) for z in stroki)); return T.proverit(p)

    def test_pass_i_preduprezhdenie(self):
        r = self.zap([FILL]); self.assertEqual(r["verdikt"], "TAX_A_PASS"); self.assertIn("preduprezhdenie", r)

    def test_fail(self):
        r = self.zap([dict(FILL, fee=None, t_ms=1792080000)]); self.assertEqual(r["verdikt"], "TAX_A_FAIL")
        self.assertIn("fee", r["primery"][1]); self.assertTrue(any("миллисекундах" in x for x in r["primery"][1]))

    def test_sekret(self):
        r = self.zap([dict(FILL, note="api_key=zzz")]); self.assertEqual(r["verdikt"], "TAX_A_FAIL")


if __name__ == "__main__":
    unittest.main()
