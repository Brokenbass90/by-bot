from dataclasses import replace

from scripts.audit_funding_positioning_v2 import Trade
from scripts import audit_funding_positioning_v4_maker as v4


def _trade(side: int = 1) -> Trade:
    return Trade(
        symbol="ALTUSDT",
        event_ts=0,
        entry_ts=1_000,
        exit_ts=61_000,
        side=side,
        funding_rate=-0.001 if side > 0 else 0.001,
        regime="neutral",
        asset_return=0.01,
        btc_return=0.0,
        funding_cashflow=0.0,
    )


def test_long_requires_strict_trade_through(monkeypatch):
    rows = (
        (1_000, 100.0, 100.2, 99.95, 100.0, 1.0),
        (301_000, 100.0, 100.1, 99.94, 100.0, 1.0),
        (58_001_000, 101.0, 101.0, 101.0, 101.0, 1.0),
    )
    btc = tuple(replace_row(row, open_price=100.0) for row in rows)
    monkeypatch.setattr(v4, "_bars", lambda symbol: rows if symbol == "ALTUSDT" else btc)
    monkeypatch.setattr(v4, "_funding", lambda symbol: ())
    # 5 bps below 100 is 99.95. A touch is not a fill; 99.94 is.
    result = v4._maker_fill(_trade(), offset_bps=5, timeout_minutes=60, hold_hours=16)
    assert result is not None
    assert result.entry_ts == 301_000
    assert result.asset_return > 0


def test_nonfill_is_zero_in_per_signal_economics(monkeypatch):
    monkeypatch.setattr(v4, "_maker_fill", lambda *args, **kwargs: None)
    result = v4.run_offset(
        [(_trade(), 0.0, 0.02)],
        offset_bps=5,
        timeout_minutes=60,
        hold_hours=16,
        maker_round_trip_bps=6,
    )
    assert result["fill_rate"] == 0.0
    assert result["realized_per_submitted_signal"]["mean_bps"] == 0.0
    assert result["nonfill_market_counterfactual"]["mean_bps"] == 194.0


def replace_row(row, *, open_price):
    values = list(row)
    values[1] = open_price
    return tuple(values)
