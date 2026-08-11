import csv
from pathlib import Path

import pytest

from research_lab.negative_trade_lab import analyze, write_outputs


FIELDS = [
    "strategy", "symbol", "side", "entry_ts", "exit_ts", "entry_price",
    "initial_sl", "pnl", "fees", "reason", "signal_reason", "initial_risk_usd",
]


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _row(symbol: str, entry: int, pnl: float, fees: float, reason: str) -> dict:
    return {
        "strategy": "s", "symbol": symbol, "side": "long",
        "entry_ts": entry, "exit_ts": entry + 3_600_000,
        "entry_price": 100, "initial_sl": 99, "pnl": pnl, "fees": fees,
        "reason": reason,
        "signal_reason": "squeeze 30% of max, vol×3.0, ATR 1.0%, regime=bull_chop, htf=long",
        "initial_risk_usd": 10,
    }


def test_cost_killed_case_and_exit_paths(tmp_path):
    path = tmp_path / "trades.csv"
    _write(path, [
        _row("AAAUSDT", 1_700_000_000_000, -1, 4, "x+TP1+TRAIL_SL"),
        _row("BBBUSDT", 1_700_010_000_000, -1, 4, "x+TRAIL_SL"),
        _row("CCCUSDT", 1_700_020_000_000, -1, 4, "x+SL"),
    ])

    payload = analyze([path])

    assert payload["diagnostic_class"] == "positive_gross_edge_killed_by_costs"
    assert payload["overall"]["net_r"] == pytest.approx(-0.3)
    assert payload["overall"]["gross_r"] == pytest.approx(0.9)
    assert payload["overall"]["cost_r"] == pytest.approx(1.2)
    paths = {row["bucket"] for row in payload["phenotypes"] if row["dimension"] == "exit_path"}
    assert paths == {"TP1+TRAIL_SL", "TRAIL_SL", "SL"}


def test_duplicate_is_reported_and_not_double_counted(tmp_path):
    path = tmp_path / "trades.csv"
    row = _row("AAAUSDT", 1_700_000_000_000, -5, 1, "x+SL")
    _write(path, [row, row])

    payload = analyze([path])

    assert payload["quality"]["status"] == "warn"
    assert payload["quality"]["duplicate_count"] == 1
    assert payload["overall"]["trades"] == 1


def test_outputs_include_proposal_only_ai_packet(tmp_path):
    path = tmp_path / "trades.csv"
    _write(path, [_row("AAAUSDT", 1_700_000_000_000, -5, 1, "x+SL")])
    payload = analyze([path])

    outputs = write_outputs(payload, tmp_path / "out", "case")

    assert Path(outputs["analysis"]).exists()
    packet = Path(outputs["ai_packet"]).read_text(encoding="utf-8")
    assert "proposal_only" in packet
    assert "no_live_mutation" in packet
