import unittest

from scripts.equities_alpaca_paper_bridge import _trail_stop_triggered


class TestAlpacaMonthlyTrailing(unittest.TestCase):
    def test_peak_arms_software_trail_after_current_gain_drops_below_trigger(self):
        state = {
            "GOOGL": {
                "entry_price": 382.03,
                "hwm": 406.49,
            }
        }
        position = {"current_price": 383.00}

        fired, gain, drop, peak_gain = _trail_stop_triggered(
            state,
            "GOOGL",
            position,
            trail_pct=0.035,
            min_gain_pct=3.5,
        )

        self.assertTrue(fired)
        self.assertLess(gain, 3.5)
        self.assertGreaterEqual(drop, 3.5)
        self.assertGreaterEqual(peak_gain, 3.5)

    def test_trail_does_not_arm_without_peak_gain(self):
        state = {"AMD": {"entry_price": 100.0, "hwm": 102.0}}
        position = {"current_price": 97.0}

        fired, _, drop, peak_gain = _trail_stop_triggered(
            state,
            "AMD",
            position,
            trail_pct=0.02,
            min_gain_pct=3.5,
        )

        self.assertFalse(fired)
        self.assertGreaterEqual(drop, 2.0)
        self.assertLess(peak_gain, 3.5)


if __name__ == "__main__":
    unittest.main()
