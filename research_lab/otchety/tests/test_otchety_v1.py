import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sobytiya_v1 as S, tekst_tg as T

KITY = dict(command_id="1", go_ms=1000, entry_dispatch_deadline_ms=61000, finality_ms=99000, observation_completed_ms=120000,
            planned_ten_leg_gross_usdt="173.8", actual_entry_gross_usdt="102.3", required_legs=10, filled_legs=2,
            not_attempted_legs=["XPLUSDT"], entry_intent_offsets_ms=[dict(symbol="BTWUSDT", after_go_ms=12003)],
            per_symbol=dict(BTWUSDT=dict(side="Buy", entry_quantity=10, native_stop_full_quantity=10, fees_usdt="0.0196"),
                            XAUTUSDT=dict(side="Sell", entry_quantity=0.004, native_stop_full_quantity=0.004, fees_usdt="0.0184")),
            unwind_reason="DEADLINE", gross_pnl_usdt="0.05802", fees_usdt="0.12331398", funding_usdt="0", terminal_net_usdt="-0.06529398",
            broker_flat_proven=True, exchange_create_rejections=0)


class T1(unittest.TestCase):
    def test_kity(self):
        ev = S.iz_kity_terminal(KITY); self.assertEqual([e["type"] for e in ev], ["FAILED_SAFE_FLAT", "ACCOUNTING_FINAL"])
        f = ev[0]; self.assertTrue(f["owner_flat"]); self.assertEqual(len(f["legs"]), 3)
        self.assertEqual([l["side"] for l in f["legs"]][:2], ["long", "short"])
        self.assertIn("НЕПОЛНАЯ КОРЗИНА 2/10", T.podpis(f)); self.assertIn("▼ −0.0653", T.podpis(f))

    def test_uchet_soglasovan(self):
        b = dict(type="ACCOUNTING_FINAL", ts_ms=1, sleeve="A", venue="v", strategy="s", evidence_id="e", mode="LIVE", ccy="USD")
        S.proverit(dict(b, gross_pnl=1.0, fees=0.1, funding=-0.05, net_pnl=0.85))
        with self.assertRaises(S.OshibkaSobytiya): S.proverit(dict(b, gross_pnl=1.0, fees=0.1, funding=0.0, net_pnl=1.0))

    def test_lenta_i_polya(self):
        e = dict(type="ENTRY_FILLED", ts_ms=1, sleeve="ALPACA", venue="Alpaca", strategy="NET_DYNAMIC", evidence_id="j#1", mode="LIVE",
                 symbol="NET", side="long", qty=0.325, px=311.222, ccy="USD", stop_px=277.69)
        l = S.dlya_lenty(e); self.assertEqual((l["event"], l["fill_price"], l["sl_price"], l["side"]), ("entry_filled", 311.222, 277.69, "Buy"))
        with self.assertRaises(S.OshibkaSobytiya): S.proverit(dict(e, evidence_id=None))
        with self.assertRaises(S.OshibkaSobytiya): S.proverit(dict(e, type="EXIT_FILLED"))


if __name__ == "__main__":
    unittest.main()
