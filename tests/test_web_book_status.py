import asyncio
import json
from pathlib import Path

from web.routes import data_routes


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_book_status_uses_runtime_ledgers_without_authorizing_capital(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(data_routes, "_RUNTIME_ROOT", tmp_path)
    _write_json(
        tmp_path / "bot_heartbeat.json",
        {
            "regime": "bear_chop",
            "strategy_runtime_config": {
                "enabled": {"att1": True},
                "risk_mult": {"att1": 0.1, "bounce1": 0.0},
                "breaker": {"att1": {"trades": 8, "blocked": False}},
            },
        },
    )
    _write_json(
        tmp_path / "arb" / "arb_roi_estimate.json",
        {
            "sample": {
                "closed_cycles": 12,
                "median_return_pct_total_capital_per_cycle": -0.16,
                "p25_return_pct_total_capital_per_cycle": -0.22,
            },
            "promotion_decision": {
                "initial_gate_cycles": 20,
                "provisional_economics_positive": False,
            },
        },
    )
    _write_json(
        tmp_path / "funding_positioning_v4_shadow_summary.json",
        {"trials": 8, "submitted": 3, "fills": 1, "closed": 0},
    )
    _write_jsonl(
        tmp_path / "xsec_v3_shadow" / "ledger.jsonl",
        [{"decision_id": "a"}, {"decision_id": "a"}, {"decision_id": "b"}],
    )
    _write_jsonl(
        tmp_path / "alpaca_adaptive_v1_shadow_ledger.jsonl",
        [{"decision_id": "c"}],
    )

    payload = asyncio.run(data_routes.get_book_status(_="tester"))
    rows = {row["sleeve"]: row for row in payload["sleeves"]}

    assert payload["live_money_sleeves"] == ["ATT1 short"]
    assert rows["ATT1 short"]["sample_n"] == 8
    assert rows["XSEC"]["sample_n"] == 2
    assert rows["Cross-exchange funding"]["remaining"] == 8
    assert rows["Funding positioning V4"]["capital_authorized"] is False
