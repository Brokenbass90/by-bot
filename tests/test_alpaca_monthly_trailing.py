import unittest

from scripts.equities_alpaca_paper_bridge import Pick, _select_monthly_cycle_picks, _trail_stop_triggered


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


class TestAlpacaMonthlySelection(unittest.TestCase):
    def _pick(self, ticker: str) -> Pick:
        return Pick(
            month="2026-06",
            ticker=ticker,
            entry_day="2026-06-12",
            score=1.0,
            atr20_pct=2.0,
            momentum20_pct=3.0,
            momentum60_pct=8.0,
            pullback60_pct=-4.0,
            universe_score=1.0,
        )

    def test_uses_next_best_when_top_picks_are_reentry_blocked(self):
        picks = [self._pick(t) for t in ("DDOG", "QCOM", "NOW", "SNOW", "CRWD", "XOM")]

        selected = _select_monthly_cycle_picks(
            picks,
            earnings_blocked={},
            blocked_reentry_symbols={"DDOG", "QCOM", "NOW"},
            max_positions=4,
            no_current_cycle=False,
        )

        assert [p.ticker for p in selected] == ["SNOW", "CRWD", "XOM"]

    def test_no_current_cycle_stays_flat(self):
        selected = _select_monthly_cycle_picks(
            [self._pick("DDOG")],
            earnings_blocked={},
            blocked_reentry_symbols=set(),
            max_positions=4,
            no_current_cycle=True,
        )

        assert selected == []


if __name__ == "__main__":
    unittest.main()
