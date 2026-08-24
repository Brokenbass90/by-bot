from __future__ import annotations

from research_lab.summarize_att1_sbr1_presealed_economics import (
    DiagnosticViolation,
    chronological_symbol_occupancy,
    metrics,
    zero_risk_shadow_gate,
)


def _row(
    signal_id: str,
    ts: int,
    deadline: int,
    net_r: str,
    symbol: str = "BTCUSDT",
    *,
    exit_ts: int | None = None,
):
    return {
        "schema_id": "research_live_adapter_parity_v2",
        "sleeve_id": "SBR1",
        "release_or_promotion_authority": False,
        "exception": None,
        "bar_ts": ts,
        "fill_ts_ms": ts,
        "exit_ts_ms": deadline if exit_ts is None else exit_ts,
        "time_stop": {"deadline_ms": deadline},
        "symbol": symbol,
        "signal_id": signal_id,
        "net_r": net_r,
    }


def test_chronological_occupancy_uses_actual_exit() -> None:
    rows = [
        _row("a", 1_000, 5_000, "1", exit_ts=3_000),
        _row("b", 2_000, 6_000, "9"),
        _row("c", 2_000, 6_000, "2", "ETHUSDT"),
        _row("d", 3_000, 8_000, "-1"),
    ]
    result = chronological_symbol_occupancy(rows, "SBR1")
    assert [row["signal_id"] for row in result.rows] == ["a", "c", "d"]
    assert result.overlap_drops == 1


def test_duplicate_signal_id_fails_closed() -> None:
    rows = [
        _row("same", 1_000, 2_000, "1"),
        _row("same", 2_000, 3_000, "1", "ETHUSDT"),
    ]
    try:
        chronological_symbol_occupancy(rows, "SBR1")
    except DiagnosticViolation as exc:
        assert str(exc) == "duplicate_signal_id"
    else:
        raise AssertionError("duplicate signal must fail closed")


def test_metrics_and_shadow_gate_are_explicitly_non_money() -> None:
    rows = []
    symbols = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT",
        "LINKUSDT", "LTCUSDT", "DOTUSDT", "SUIUSDT",
    ]
    for index in range(48):
        symbol = symbols[index % len(symbols)]
        value = "-0.5" if index % 7 == 0 else "1"
        rows.append(_row(str(index), 1_700_000_000_000 + index * 86_400_000,
                         1_700_000_000_001 + index * 86_400_000, value, symbol))
    report = metrics(rows)
    gate = zero_risk_shadow_gate(report)
    assert report["n"] == 48
    assert gate["decision"] == "PASS_ZERO_RISK_SHADOW_ONLY"
    assert gate["money_authority"] is False
    assert gate["authority"] == "prospective_zero_risk_shadow_only"
