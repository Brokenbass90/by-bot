import unittest
import json
from pathlib import Path
import fcntl
import os

import scripts.equities_alpaca_paper_bridge as bridge
from datetime import datetime, timezone

from scripts.equities_alpaca_paper_bridge import (
    Pick,
    _accepted_floor_preflight_violations,
    _active_reentry_blocks,
    _add_reentry_block,
    _broker_protection_policy_violations,
    _broker_truth_snapshot,
    _broker_stop_rearm_symbols,
    _default_broker_protection_tif,
    _entry_relative_stop_price,
    _hard_capped_normalized_weights,
    _new_entry_allowed,
    _persistent_exit_tif_for_qty,
    _protected_rearm_stop_price,
    _quantity_for_notional,
    _select_monthly_cycle_picks,
    _single_covering_stop_needing_update,
    _save_hwm_state,
    _save_reentry_block_state,
    _trail_stop_triggered,
)


class TestAlpacaMonthlyTrailing(unittest.TestCase):
    def test_whole_share_quantity_is_floored_without_exceeding_budget(self):
        qty, reason = _quantity_for_notional(350.0, 100.0, whole_share_only=True)

        self.assertEqual(qty, 3.0)
        self.assertEqual(reason, "")
        self.assertLessEqual(qty * 100.0, 350.0)

    def test_whole_share_quantity_rejects_candidate_below_one_share(self):
        qty, reason = _quantity_for_notional(80.0, 100.0, whole_share_only=True)

        self.assertIsNone(qty)
        self.assertEqual(reason, "whole_share_budget_below_one_share")

    def test_fractional_quantity_policy_is_unchanged_by_default(self):
        qty, reason = _quantity_for_notional(80.0, 100.0, whole_share_only=False)

        self.assertEqual(qty, 0.8)
        self.assertEqual(reason, "")

    def test_broad_default_is_overridden_by_exact_quantity_policy(self):
        self.assertEqual(_default_broker_protection_tif("simple_stop"), "gtc")
        self.assertEqual(_default_broker_protection_tif("bracket"), "day")

    def test_exit_tif_obeys_alpaca_fractional_order_matrix(self):
        self.assertEqual(_persistent_exit_tif_for_qty("gtc", 0.563776973), "day")
        self.assertEqual(_persistent_exit_tif_for_qty("day", 0.135734866), "day")
        self.assertEqual(_persistent_exit_tif_for_qty("day", 1.0), "gtc")
        self.assertEqual(_persistent_exit_tif_for_qty("gtc", 2.0), "gtc")
        self.assertEqual(_persistent_exit_tif_for_qty("day", 1.5), "day")
        self.assertEqual(_persistent_exit_tif_for_qty("day", 1.0), "gtc")
        self.assertEqual(_persistent_exit_tif_for_qty("day", 0.999999999), "day")
        self.assertEqual(_persistent_exit_tif_for_qty("day", 1.000000001), "day")

    def test_single_covering_day_stop_is_updated_only_for_whole_qty_policy(self):
        stop = {
            "id": "day-stop",
            "qty": "0.563776973",
            "filled_qty": "0",
            "time_in_force": "day",
            "stop_price": "108.20",
            "type": "stop",
        }
        fractional_tif = _persistent_exit_tif_for_qty("gtc", 0.563776973)
        self.assertIsNone(_single_covering_stop_needing_update(
            [stop],
            0.563776973,
            fractional_tif,
            108.20,
        ))
        whole_stop = {**stop, "qty": "1"}
        selected = _single_covering_stop_needing_update(
            [whole_stop],
            1.0,
            _persistent_exit_tif_for_qty("day", 1.0),
            108.20,
        )
        self.assertIs(selected, whole_stop)

    def test_covering_fractional_day_stop_is_raised_when_hwm_floor_is_higher(self):
        stop = {
            "id": "day-stop",
            "qty": "0.563776973",
            "filled_qty": "0",
            "time_in_force": "day",
            "stop_price": "96.47",
            "type": "stop",
        }
        selected = _single_covering_stop_needing_update(
            [stop],
            0.563776973,
            "day",
            108.20,
        )
        self.assertIs(selected, stop)
        self.assertIsNone(
            _single_covering_stop_needing_update(
                [{**stop, "type": "trailing_stop"}],
                0.563776973,
                "day",
                108.20,
            )
        )

    def test_rearm_floor_uses_only_reconciled_protective_hwm(self):
        position = {
            "symbol": "ABBV",
            "qty": "0.135734866",
            "avg_entry_price": "247.55",
            "current_price": "265.50",
        }
        state = {
            "ABBV": {
                "entry_price": 247.55,
                "hwm": 266.71,
                "qty": 0.135734866,
                "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00Z",
                "accepted_stop_floor": 257.37,
            }
        }
        protected = _protected_rearm_stop_price(
            "ABBV",
            235.17,
            position,
            [],
            state,
        )
        self.assertEqual(protected, 257.37)

        stale_state = {
            "ABBV": {
                "entry_price": 200.0,
                "hwm": 300.0,
                "qty": 0.135734866,
                "lifecycle_first_seen_at_utc": "2026-08-01T13:30:00Z",
                "accepted_stop_floor": 290.0,
            }
        }
        self.assertEqual(
            _protected_rearm_stop_price(
                "ABBV",
                235.17,
                position,
                [],
                stale_state,
            ),
            235.17,
        )

        hwm_only = {
            "ABBV": {
                "entry_price": 247.55,
                "hwm": 300.0,
                "qty": 0.135734866,
                "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00Z",
            }
        }
        self.assertEqual(
            _protected_rearm_stop_price("ABBV", 235.17, position, [], hwm_only),
            235.17,
        )

    def test_rearm_never_lowers_an_existing_broker_stop(self):
        protected = _protected_rearm_stop_price(
            "SCHW",
            96.47,
            {"qty": "0.5", "avg_entry_price": "101.552"},
            [{"stop_price": "109.25"}],
            {},
        )
        self.assertEqual(protected, 109.25)

    def test_existing_lifecycle_must_have_authoritative_floor_before_mutation(self):
        position = {
            "symbol": "SCHW",
            "qty": "0.563776973",
            "avg_entry_price": "101.552",
        }
        state = {
            "SCHW": {
                "entry_price": 101.552,
                "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00Z",
                "accepted_stop_floor": 108.20,
            }
        }
        self.assertEqual(
            _accepted_floor_preflight_violations(
                positions=[position],
                intraday_managed_symbols=set(),
                protective_floor_state=state,
                state_error="",
            ),
            [],
        )
        missing = _accepted_floor_preflight_violations(
            positions=[position],
            intraday_managed_symbols=set(),
            protective_floor_state={},
            state_error="state_missing",
        )
        self.assertEqual(missing[0]["reason"], "protective_floor_state_not_authoritative")
        mismatched = _accepted_floor_preflight_violations(
            positions=[position],
            intraday_managed_symbols=set(),
            protective_floor_state={
                "SCHW": {
                    "entry_price": 99.0,
                    "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00Z",
                    "accepted_stop_floor": 108.20,
                }
            },
            state_error="",
        )
        self.assertEqual(mismatched[0]["reason"], "existing_lifecycle_floor_not_reconciled")

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
            self.assertIn("ALPACA_BROKER_PROTECTION_TIF=day", text)
            self.assertIn("ALPACA_NATIVE_TRAIL_TIF=day", text)

    def test_whole_share_paper_profile_is_default_off_and_fail_closed(self):
        root = Path(__file__).resolve().parents[1]
        profile = root / "configs" / "alpaca_v38_whole_share_paper_default_off.env"
        launcher = root / "scripts" / "run_alpaca_whole_share_paper_once.sh"

        profile_text = profile.read_text(encoding="utf-8")
        self.assertIn("ALPACA_WHOLE_SHARE_ONLY=1", profile_text)
        self.assertIn("ALPACA_BASE_URL=https://paper-api.alpaca.markets", profile_text)
        self.assertIn("ALPACA_SEND_ORDERS=0", profile_text)
        self.assertIn("ALPACA_ALLOW_NEW_ENTRIES=0", profile_text)
        self.assertIn("ALPACA_TARGET_ALLOC_PCT=0.70", profile_text)
        self.assertIn("ALPACA_BROKER_PROTECTION_REQUIRED=1", profile_text)
        self.assertIn("ALPACA_BROKER_PROTECTION_TIF=gtc", profile_text)
        self.assertIn("ALPACA_NATIVE_TRAIL_ENABLE=0", profile_text)
        self.assertIn(
            "ALPACA_AUTOPILOT_RUNTIME_DIR=runtime/equities_monthly_v38_whole_share_paper",
            profile_text,
        )
        self.assertIn(
            "MONTHLY_HWM_STATE_PATH=runtime/equities_monthly_v38_whole_share_paper/monthly_hwm.json",
            profile_text,
        )
        self.assertIn(
            "MONTHLY_REENTRY_BLOCK_STATE_PATH=runtime/equities_monthly_v38_whole_share_paper/reentry_block.json",
            profile_text,
        )

        launcher_text = launcher.read_text(encoding="utf-8")
        self.assertNotIn("--send-orders", launcher_text)
        self.assertIn("ALPACA_SEND_ORDERS=0", launcher_text)
        self.assertIn("ALPACA_ALLOW_NEW_ENTRIES=0", launcher_text)

    def test_live_wrapper_sources_the_same_protective_exit_parameters(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "scripts/run_alpaca_live_v38_once.sh").read_text(encoding="utf-8")
        protective_at = text.index("source configs/alpaca_protective_exit.env")
        safe_hold_at = text.index("source configs/alpaca_live_v38_safe_hold.env")
        self.assertLess(protective_at, safe_hold_at)

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

    def test_exact_protection_policy_accepts_fractional_day_stop_at_floor(self):
        violations = _broker_protection_policy_violations(
            positions=[
                {
                    "symbol": "SCHW",
                    "qty": "0.563776973",
                    "avg_entry_price": "101.552",
                }
            ],
            open_orders=[
                {
                    "id": "stop-1",
                    "symbol": "SCHW",
                    "side": "sell",
                    "type": "stop",
                    "status": "new",
                    "qty": "0.563776973",
                    "filled_qty": "0",
                    "stop_price": "108.20",
                    "time_in_force": "day",
                }
            ],
            intraday_managed_symbols=set(),
            protective_floor_state={
                "SCHW": {
                    "entry_price": 101.552,
                    "lifecycle_first_seen_at_utc": "2026-08-10T13:30:00Z",
                    "accepted_stop_floor": 108.20,
                }
            },
            requested_tif="gtc",
        )
        assert violations == []

    def test_exact_protection_policy_rejects_low_floor_wrong_tif_and_missing_state(self):
        base = {
            "id": "stop-1",
            "symbol": "SCHW",
            "side": "sell",
            "type": "stop",
            "status": "new",
            "qty": "0.563776973",
            "filled_qty": "0",
            "stop_price": "96.47",
            "time_in_force": "gtc",
        }
        violations = _broker_protection_policy_violations(
            positions=[
                {
                    "symbol": "SCHW",
                    "qty": "0.563776973",
                    "avg_entry_price": "101.552",
                }
            ],
            open_orders=[base],
            intraday_managed_symbols=set(),
            protective_floor_state={},
            requested_tif="gtc",
        )
        reasons = {row["reason"] for row in violations}
        assert reasons == {
            "fixed_stop_tif_mismatch",
            "accepted_stop_floor_not_reconciled",
        }

    def test_bridge_single_writer_lock_fails_closed(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            path = os.path.join(directory, "alpaca.lock")
            previous = os.environ.get("ALPACA_BRIDGE_LOCK_PATH")
            previous_wait = os.environ.get("ALPACA_WRITER_LOCK_WAIT_SEC")
            os.environ["ALPACA_BRIDGE_LOCK_PATH"] = path
            os.environ["ALPACA_WRITER_LOCK_WAIT_SEC"] = "0"
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
                if previous_wait is None:
                    os.environ.pop("ALPACA_WRITER_LOCK_WAIT_SEC", None)
                else:
                    os.environ["ALPACA_WRITER_LOCK_WAIT_SEC"] = previous_wait


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
