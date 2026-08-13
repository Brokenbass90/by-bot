from scripts.audit_alpaca_clean_v38_proxy_v1 import audit


def test_audit_detects_arithmetic_drift():
    result = {
        "decisions": [{"symbols": ["A"], "unknown_sector_symbols": ["A"]}],
        "results": {
            "base": {
                "initial_capital": 100.0,
                "final_equity": 110.0,
                "return_pct": 10.0,
                "daily_max_drawdown_pct": 0.0,
                "profit_factor_realized": float("inf"),
                "realized_trades": 1,
                "red_months": 0,
                "months": 2,
                "worst_month_pct": 0.0,
                "average_gross_exposure_pct": 0.0,
                "daily_equity": [
                    {"session": "2026-01-30", "equity": 100.0, "gross_exposure": 0.0},
                    {"session": "2026-02-27", "equity": 110.0, "gross_exposure": 0.0},
                ],
                "trades": [{"entry_session": "2026-02-01", "exit_session": "2026-02-02", "entry_fill": 10.0, "exit_fill": 11.0, "qty": 1.0, "pnl": 10.0}],
            }
        },
    }
    assert audit(result)["passed"] is True
    result["results"]["base"]["return_pct"] = 99.0
    receipt = audit(result)
    assert receipt["passed"] is False
    assert "base:return_pct" in receipt["failures"]
