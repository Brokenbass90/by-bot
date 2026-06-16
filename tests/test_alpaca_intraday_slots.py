#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_monthly_positions_do_not_consume_intraday_slots():
    from scripts.equities_alpaca_intraday_bridge import _position_slot_views

    intraday, visible = _position_slot_views(
        state_symbols=[],
        remote_only_symbols=[],
        protected_remote_symbols=["AMD", "GE", "LLY", "SNOW"],
        pending_close_symbols=[],
    )

    assert intraday == []
    assert visible == ["AMD", "GE", "LLY", "SNOW"]


def test_intraday_slots_still_count_intraday_and_unknown_remote_positions():
    from scripts.equities_alpaca_intraday_bridge import _position_slot_views

    intraday, visible = _position_slot_views(
        state_symbols=["TSLA"],
        remote_only_symbols=["JPM"],
        protected_remote_symbols=["AMD"],
        pending_close_symbols=["GOOGL"],
    )

    assert intraday == ["GOOGL", "JPM", "TSLA"]
    assert visible == ["AMD", "GOOGL", "JPM", "TSLA"]
