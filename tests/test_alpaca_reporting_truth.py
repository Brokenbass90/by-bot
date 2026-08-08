from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


digest = _load("tg_daily_digest_truth_test", "scripts/tg_daily_digest.py")
report = _load("equities_alpaca_tg_report_truth_test", "scripts/equities_alpaca_tg_report.py")
watchdog = _load("alpaca_report_watchdog_truth_test", "scripts/alpaca_report_freshness_watchdog.py")


def _positions():
    return [
        {
            "symbol": "ABBV",
            "side": "long",
            "qty": "0.07194000",
            "unrealized_pl": "0.12",
            "unrealized_plpc": "0.0021",
            "unrealized_intraday_pl": "0.05",
        },
        {
            "symbol": "GE",
            "side": "long",
            "qty": "0.06154",
            "unrealized_pl": "-0.04",
            "unrealized_plpc": "-0.001",
            "unrealized_intraday_pl": "-0.02",
        },
    ]


def _orders():
    return [
        {
            "id": "parent",
            "status": "new",
            "type": "limit",
            "symbol": "ABBV",
            "side": "sell",
            "legs": [
                {
                    "id": "abbv-stop",
                    "status": "new",
                    "type": "stop",
                    "symbol": "ABBV",
                    "side": "sell",
                    "qty": "0.07194",
                    "filled_qty": "0",
                }
            ],
        }
    ]


def test_fractional_stop_coverage_reads_nested_orders():
    result = digest._stop_coverage(_positions(), _orders())
    assert result["covered"] == ["ABBV"]
    assert result["missing"] == ["GE"]
    assert result["covered_count"] == 1
    assert digest._fmt_qty("0.07194000") == "0.07194"


def test_account_metrics_use_last_equity_base_hwm_and_supported_pnl(monkeypatch):
    monkeypatch.setenv("ALPACA_REPORT_BASE_CAPITAL_USD", "500")
    metrics = digest._account_metrics(
        {"equity": "486", "last_equity": "485"},
        _positions(),
        {"equity": ["500", "510", "486"]},
    )
    assert metrics["day_pnl"] == 1.0
    assert round(metrics["open_unrealized"], 8) == 0.08
    assert round(metrics["intraday_unrealized"], 8) == 0.03
    assert round(metrics["realized_day_est"], 8) == 0.97
    assert metrics["peak"] == 510.0
    assert round(metrics["dd_pct"], 4) == round((486 / 510 - 1) * 100, 4)


def test_intraday_v1_is_data_invalid_until_strict_broker_fill_proof(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "ROOT", tmp_path)
    assert digest._intraday_v1_ledger_status() == "DATA_INVALID"
    proof = tmp_path / "runtime" / "equities_intraday_dynamic_v1" / "ledger_reconciliation.json"
    proof.parent.mkdir(parents=True)
    proof.write_text('{"status":"VERIFIED","source":"estimates"}', encoding="utf-8")
    assert digest._intraday_v1_ledger_status() == "DATA_INVALID"
    proof.write_text('{"status":"VERIFIED","source":"broker_fills"}', encoding="utf-8")
    assert digest._intraday_v1_ledger_status() == "VERIFIED"


def test_report_reads_trail_setting_from_manager_profile_when_env_is_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("MONTHLY_TRAIL_ENABLE", raising=False)
    profile = tmp_path / "manager.env"
    profile.write_text("MONTHLY_TRAIL_ENABLE=1\n", encoding="utf-8")
    assert digest._configured_env_bool("MONTHLY_TRAIL_ENABLE", profile) is True
    assert report._configured_env_bool("MONTHLY_TRAIL_ENABLE", profile) is True


def test_monthly_report_ignores_zero_padded_equity_history(monkeypatch):
    monkeypatch.setattr(report, "get_account", lambda: {"equity": "484.66", "cash": "391.27"})
    monkeypatch.setattr(
        report,
        "get_portfolio_history",
        lambda **_kwargs: {"equity": [0, None, "483.50", "484.66"]},
    )
    monkeypatch.setattr(report, "get_closed_orders", lambda **_kwargs: [])
    monkeypatch.setattr(report, "get_positions", lambda: [])
    monkeypatch.setattr(report, "get_open_orders", lambda: [])
    monkeypatch.setattr(report, "_read_current_cycle_picks", lambda: ("2026-08", []))
    monkeypatch.setattr(report, "_intraday_ledger_verified", lambda: False)
    monkeypatch.setattr(report, "_alpaca_ai_note", lambda **_kwargs: "")

    text = report.monthly_report()

    assert "Start equity: $483.50" in text
    assert "End equity:   <b>$484.66</b>" in text
    assert "+1.16 (+0.24%)" in text
    assert "48466" not in text


def test_monthly_digest_tells_live_safe_hold_broker_truth(tmp_path, monkeypatch):
    monkeypatch.setattr(digest, "ROOT", tmp_path)
    monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
    monkeypatch.setenv("ALPACA_SEND_ORDERS", "0")
    monkeypatch.setenv("ALPACA_ALLOW_NEW_ENTRIES", "0")
    monkeypatch.setenv("ALPACA_CLOSE_STALE_POSITIONS", "0")
    monkeypatch.setenv("MONTHLY_TRAIL_ENABLE", "1")
    monkeypatch.setenv("ALPACA_REPORT_BASE_CAPITAL_USD", "500")

    picks = tmp_path / "runtime" / "equities_monthly_v36" / "current_cycle_picks.csv"
    picks.parent.mkdir(parents=True)
    picks.write_text("month,ticker\n2026-07,ABBV\n2026-07,ABNB\n", encoding="utf-8")

    def fake_get(path: str):
        if path == "/v2/positions":
            return _positions()
        if path == "/v2/account":
            return {"equity": "486", "last_equity": "485", "cash": "328", "buying_power": "328"}
        if path.startswith("/v2/orders"):
            return _orders()
        if path.startswith("/v2/account/portfolio/history"):
            return {"equity": [500, 510, 486]}
        raise AssertionError(path)

    monkeypatch.setattr(digest, "_alpaca_get", fake_get)
    text = digest._alpaca_monthly_section()
    assert "LIVE BROKER" in text
    assert "Report order-submit=OFF" in text
    assert "new entries=OFF" in text and "SAFE-HOLD" in text
    assert "software trail config=ON (requires the scheduled manager poll)" in text
    assert "Base $500.00" in text and "DD от max(base/HWM $510.00)" in text
    assert "Current research picks (не holdings): ABBV, ABNB" in text
    assert "Actual broker holdings: ABBV, GE" in text
    assert "Picks, которых нет у брокера: ABNB" in text
    assert "Holdings вне current picks: GE" in text
    assert "qty=0.07194" in text
    assert "Broker stop coverage: <b>1/2</b>" in text
    assert "DATA_INVALID" in text


def test_equities_report_send_failure_is_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "RUNTIME_REPORT_DIR", tmp_path)
    monkeypatch.setattr(report, "daily_report", lambda: "truth report")
    monkeypatch.setattr(report, "_tg_send", lambda _msg: False)
    monkeypatch.setattr(sys, "argv", ["equities_alpaca_tg_report.py", "--no-chart"])
    monkeypatch.setattr(report, "ALPACA_KEY", "key")
    monkeypatch.setattr(report, "ALPACA_SECRET", "secret")
    assert report.main() == 1
    status = (tmp_path / "alpaca_postclose_status.json").read_text(encoding="utf-8")
    assert '"success": false' in status


def test_postclose_watchdog_requires_real_same_day_delivery():
    now = datetime(2026, 7, 10, 23, 0, tzinfo=timezone.utc)  # Friday
    assert watchdog.evaluate_delivery({}, now)["reason"] == "status_missing"
    dry = {
        "attempted_at_utc": "2026-07-10T22:10:00+00:00",
        "success": True,
        "dry_run": True,
    }
    assert watchdog.evaluate_delivery(dry, now)["reason"] == "dry_run_not_delivery"
    sent = {**dry, "dry_run": False}
    assert watchdog.evaluate_delivery(sent, now)["ok"] is True
    weekend = datetime(2026, 7, 11, 23, 0, tzinfo=timezone.utc)
    assert watchdog.evaluate_delivery({}, weekend) == {"due": False, "ok": True, "reason": "not_due"}


def test_managed_cron_has_one_morning_digest_without_postclose_duplicates():
    text = (ROOT / "scripts" / "setup_server_crons.sh").read_text(encoding="utf-8")
    assert text.count("python3 scripts/tg_daily_digest.py >>") == 1
    assert "0 8 * * *" in text
    assert "--alpaca-only --status-key alpaca_postclose" not in text
    assert "alpaca_report_freshness_watchdog.py >>" not in text
