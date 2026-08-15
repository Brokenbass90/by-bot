import unittest
import json
from pathlib import Path
import fcntl
import os

import scripts.equities_alpaca_paper_bridge as bridge
from datetime import datetime, timezone

from scripts.equities_alpaca_paper_bridge import (
    Pick,
    _active_reentry_blocks,
    _add_reentry_block,
    _broker_truth_snapshot,
    _broker_stop_rearm_symbols,
    _default_broker_protection_tif,
    _entry_relative_stop_price,
    _hard_capped_normalized_weights,
    _new_entry_allowed,
    _select_monthly_cycle_picks,
    _save_hwm_state,
    _save_reentry_block_state,
    _trail_stop_triggered,
)


class TestAlpacaMonthlyTrailing(unittest.TestCase):
    def test_simple_stop_defaults_to_gtc_so_ratchet_survives_session_boundary(self):
        self.assertEqual(_default_broker_protection_tif("simple_stop"), "gtc")
        self.assertEqual(_default_broker_protection_tif("bracket"), "day")

    def test_entry_relative_stop_preserves_frozen_signal_risk_distance(self):
        pick = Pick(
            month="2026-08",
            ticker="BAC",
            entry_day="2026-08-03",
            score=1.0,
            atr20_pct=2.0,
            momentum20_pct=3.0,
            momentum60_pct=8.0,
            pullback60_pct=-4.0,
            universe_score=1.0,
            entry_price=100.0,
            stop_price=94.0,
        )

        stop = _entry_relative_stop_price(
            pick,
            filled_avg_price=103.0,
            fallback_stop_loss_pct=0.08,
        )

        self.assertEqual(stop, 97.0)

    def test_entry_relative_stop_falls_back_to_fill_anchored_percent(self):
        pick = Pick(
            month="2026-08",
            ticker="BAC",
            entry_day="2026-08-03",
            score=1.0,
            atr20_pct=2.0,
            momentum20_pct=3.0,
            momentum60_pct=8.0,
            pullback60_pct=-4.0,
            universe_score=1.0,
        )

        stop = _entry_relative_stop_price(
            pick,
            filled_avg_price=100.0,
            fallback_stop_loss_pct=0.08,
        )

        self.assertEqual(stop, 92.0)

    def test_simple_stop_candidate_configs_pin_gtc(self):
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "configs/alpaca_v38_hybrid_top4_candidate.env",
            "configs/alpaca_v38_active_paper_candidate.env",
            "configs/alpaca_paper_v36_candidate.env",
        ):
            text = (root / relative).read_text(encoding="utf-8")
            self.assertIn("ALPACA_BROKER_PROTECTION_ORDER_CLASS=simple_stop", text)
            self.assertIn("ALPACA_BROKER_PROTECTION_TIF=gtc", text)

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

    def test_single_name_weight_cap_leaves_unused_sleeve_in_cash(self):
        weights = _hard_capped_normalized_weights({"NVDA": 10.0}, maximum_weight=0.60)

        assert weights == {"NVDA": 0.60}

    def test_dominant_name_cannot_rebreach_weight_cap(self):
        weights = _hard_capped_normalized_weights(
            {"NVDA": 10.0, "KO": 1.0, "JPM": 1.0},
            maximum_weight=0.60,
        )

        assert abs(sum(weights.values()) - 1.0) < 1e-12
        assert max(weights.values()) <= 0.60

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

    def test_broker_truth_reports_missing_stop_and_excludes_intraday(self):
        truth = _broker_truth_snapshot(
            account={"equity": "485.0", "cash": "300.0"},
            positions=[
                {"symbol": "ABBV", "qty": "1", "avg_entry_price": "100"},
                {"symbol": "GE", "qty": "1", "avg_entry_price": "200"},
                {"symbol": "AAPL", "qty": "1", "avg_entry_price": "300"},
            ],
            open_orders=[
                {"symbol": "ABBV", "side": "sell", "type": "stop", "status": "new", "qty": "1", "filled_qty": "0"},
                {"symbol": "AAPL", "side": "sell", "type": "stop", "status": "new", "qty": "1"},
                {"symbol": "GE", "side": "sell", "type": "limit", "status": "new", "qty": "1"},
            ],
            intraday_managed_symbols={"AAPL"},
        )

        assert truth["position_symbols"] == ["ABBV", "GE"]
        assert truth["stop_symbols"] == ["ABBV"]
        assert truth["missing_stop_symbols"] == ["GE"]
        assert truth["stop_coverage_count"] == 1
        assert truth["position_count"] == 2
        assert truth["stop_coverage_complete"] is False
    def test_broker_truth_requires_full_remaining_stop_quantity(self):
        truth = _broker_truth_snapshot(
            account={"equity": "485.0"},
            positions=[{"symbol": "GE", "qty": "2.0"}],
            open_orders=[
                {
                    "symbol": "GE",
                    "side": "sell",
                    "type": "stop",
                    "status": "partially_filled",
                    "qty": "2.0",
                    "filled_qty": "1.25",
                }
            ],
            intraday_managed_symbols=set(),
        )

        assert truth["protected_qty_by_symbol"]["GE"] == 0.75
        assert truth["underprotected_stop_symbols"] == ["GE"]
        assert truth["protection_gap_symbols"] == ["GE"]
        assert truth["stop_coverage_count"] == 0
        assert truth["stop_coverage_complete"] is False

    def test_broker_truth_flags_overprotected_quantity(self):
        truth = _broker_truth_snapshot(
            account={"equity": "485.0"},
            positions=[{"symbol": "GE", "qty": "1.0"}],
            open_orders=[
                {"symbol": "GE", "side": "sell", "type": "stop", "status": "new", "qty": "1.0"},
                {"symbol": "GE", "side": "sell", "type": "stop", "status": "new", "qty": "1.0"},
            ],
            intraday_managed_symbols=set(),
        )

        assert truth["overprotected_stop_symbols"] == ["GE"]
        assert truth["protection_gap_symbols"] == ["GE"]
        assert truth["stop_coverage_count"] == 0
        assert truth["stop_coverage_complete"] is False

    def test_bridge_single_writer_lock_fails_closed(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            path = os.path.join(directory, "alpaca.lock")
            previous = os.environ.get("ALPACA_BRIDGE_LOCK_PATH")
            os.environ["ALPACA_BRIDGE_LOCK_PATH"] = path
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                assert bridge.main() == 75
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                if previous is None:
                    os.environ.pop("ALPACA_BRIDGE_LOCK_PATH", None)
                else:
                    os.environ["ALPACA_BRIDGE_LOCK_PATH"] = previous


def test_hwm_state_is_atomically_replaced(tmp_path):
    path = tmp_path / "hwm.json"
    _save_hwm_state(path, {"SCHW": {"hwm": 108.25}})

    assert json.loads(path.read_text(encoding="utf-8")) == {"SCHW": {"hwm": 108.25}}
    assert list(tmp_path.glob(".hwm.json.*.tmp")) == []


def test_reentry_state_is_atomically_replaced_and_sorted(tmp_path):
    path = tmp_path / "reentry.json"
    _save_reentry_block_state(path, {"SCHW": {"blocked_until": "2026-09-01T00:00:00Z"}})

    assert json.loads(path.read_text(encoding="utf-8"))["symbols"]["SCHW"]["blocked_until"] == "2026-09-01T00:00:00Z"
    assert list(tmp_path.glob(".reentry.json.*.tmp")) == []


if __name__ == "__main__":
    unittest.main()
