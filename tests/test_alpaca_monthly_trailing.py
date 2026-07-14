import unittest
from datetime import datetime, timezone

from scripts.equities_alpaca_paper_bridge import (
    Pick,
    _active_reentry_blocks,
    _add_reentry_block,
    _broker_stop_rearm_symbols,
    _new_entry_allowed,
    _select_monthly_cycle_picks,
    _trail_stop_triggered,
)


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

    def test_safe_hold_disables_every_new_entry(self):
        assert not _new_entry_allowed("PANW", enabled=False, blocked_symbols=set())

    def test_same_cycle_stop_exit_blocks_reentry(self):
        now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
        state = {}
        _add_reentry_block(state, "PANW", now=now, days=21, reason="stop_loss_close")
        active = _active_reentry_blocks(state, now)

        assert "PANW" in active
        assert active["PANW"]["reason"] == "stop_loss_close"
        assert not _new_entry_allowed("PANW", enabled=True, blocked_symbols=set(active))

    def test_safe_hold_rearms_stale_existing_positions(self):
        symbols = _broker_stop_rearm_symbols(
            hold_symbols={"ABBV", "SCHW"},
            current_position_symbols={"ABBV", "SCHW", "GE", "AAPL"},
            intraday_managed_symbols={"AAPL"},
            close_stale_positions=False,
        )

        assert symbols == ["ABBV", "GE", "SCHW"]

    def test_rotation_mode_does_not_rearm_positions_it_will_close(self):
        symbols = _broker_stop_rearm_symbols(
            hold_symbols={"ABBV", "SCHW"},
            current_position_symbols={"ABBV", "SCHW", "GE"},
            intraday_managed_symbols=set(),
            close_stale_positions=True,
        )

        assert symbols == ["ABBV", "SCHW"]


if __name__ == "__main__":
    unittest.main()
