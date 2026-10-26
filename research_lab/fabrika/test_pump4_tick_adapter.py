import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pump4_tick_adapter import okruglit as O
K = dict(tick="0.0001", qty_step="1", min_qty="1", min_notional="5")


class T(unittest.TestCase):
    def test_short_stop_k_vhodu_i_risk_ne_rastet(self):
        r = O("short", 1.0000, 1.17637, [0.95003, 0.90009], last_price=1.0, risk_usd=3, **K)
        self.assertEqual(r["status"], "OK"); self.assertEqual(r["stop"], 1.1763)       # вниз, к входу
        self.assertEqual(r["tps"], [0.9501, 0.9001])                                    # цели — вверх, к входу
        self.assertLessEqual(r["risk_usd"], 3.0); self.assertEqual(r["qty"], 17.0)

    def test_long_zerkalno(self):
        r = O("long", 1.0, 0.82363, [1.04997], last_price=1.0, risk_usd=3, **K)
        self.assertEqual(r["stop"], 0.8237); self.assertEqual(r["tps"], [1.0499]); self.assertLessEqual(r["risk_usd"], 3.0)

    def test_block_min_notional_ne_uvelichivaet(self):
        r = O("short", 100.0, 120.0, [], last_price=100.0, risk_usd=0.5, tick="0.01", qty_step="0.01", min_qty="0.01", min_notional="5")
        self.assertEqual(r["status"], "BLOCK_MIN_NOTIONAL")

    def test_trigger_za_cenoy(self):
        r = O("short", 1.0, 1.2, [], last_price=1.25, risk_usd=3, **K)
        self.assertEqual(r["status"], "BLOCK_TRIGGER_ZA_CENOY")

    def test_tp1_ne_delitsya(self):
        r = O("short", 10.0, 12.0, [9.5], last_price=10.0, risk_usd=3, tick="0.001", qty_step="1", min_qty="1", min_notional="5")
        self.assertIn("TP1_NE_DELITSYA", r["flagi"])                                    # qty 1 → TP1 0 долей


if __name__ == "__main__":
    unittest.main()
