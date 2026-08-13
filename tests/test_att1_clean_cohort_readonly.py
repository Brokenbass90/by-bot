import json

from scripts.check_att1_clean_cohort_readonly import reconstruct


def test_clean_cohort_requires_explicit_risk_and_accounting(tmp_path):
    path = tmp_path / "events.jsonl"
    rows = [
        {"entry_order_id": "ok", "strategy": "att1_trendline_touch", "event": "entry_filled", "ts": 11,
         "actual_risk_usd": 1.0, "post_fill_risk_allowed": True, "runner": {"runner_enabled": True}},
        {"entry_order_id": "ok", "strategy": "att1_trendline_touch", "event": "close", "ts": 12,
         "accounting_contaminated": False, "pnl": 0.5, "symbol": "BTCUSDT"},
        {"entry_order_id": "bad", "strategy": "att1_trendline_touch", "event": "entry_filled", "ts": 13,
         "actual_risk_usd": 0.0, "post_fill_risk_allowed": None, "runner": {"runner_enabled": False}},
        {"entry_order_id": "bad", "strategy": "att1_trendline_touch", "event": "close", "ts": 14,
         "accounting_contaminated": False, "pnl": 1.0, "symbol": "ETHUSDT"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    result = reconstruct(path, 10)
    assert result["clean_closed"] == 1
    assert result["net_r"] == 0.5
    assert len(result["rejected"]) == 1
    assert result["gates"]["n20"] is False
