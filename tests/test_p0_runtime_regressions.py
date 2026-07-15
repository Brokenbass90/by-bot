from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

from scripts import equities_alpaca_intraday_bridge as intraday


ROOT = Path(__file__).resolve().parents[1]


def test_build_ai_full_context_script_bootstraps_repo_import() -> None:
    script = ROOT / "scripts" / "build_ai_full_context.py"
    probe = (
        "import runpy; "
        f"ns = runpy.run_path({json.dumps(str(script))}); "
        "print(ns['build_ai_brief']())"
    )

    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        cwd="/tmp",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "AI_CONTEXT_BRIEF unavailable" not in result.stdout
    assert "ПРАВИЛА" in result.stdout


def test_alpaca_close_fill_reconciliation_uses_client_base_url(monkeypatch) -> None:
    class FakeClient:
        base_url = "https://paper-api.alpaca.markets"

        @staticmethod
        def get_account() -> dict:
            return {"equity": "500", "cash": "500"}

        @staticmethod
        def list_positions() -> list:
            return []

        @staticmethod
        def list_orders(*, status: str = "open") -> list:
            assert status == "open"
            return []

    position = intraday.PositionState(
        symbol="MSFT",
        side="long",
        entry_price=100.0,
        sl_price=98.0,
        tp_price=104.0,
        qty=1.0,
        entry_ts=1,
    )
    telegram_messages: list[str] = []

    monkeypatch.setenv("INTRADAY_SPY_GATE", "0")
    monkeypatch.setenv("INTRADAY_EQUITY_CURVE_GATE", "0")
    monkeypatch.setenv("INTRADAY_MISSING_POSITION_GRACE_MINUTES", "0")
    monkeypatch.setattr(intraday, "_daily_loss_ok", lambda *_: (True, "daily ok"))
    monkeypatch.setattr(intraday, "_load_state", lambda: {"MSFT": position})
    monkeypatch.setattr(intraday, "_load_reentry_blocks", lambda *_: {})
    monkeypatch.setattr(
        intraday,
        "_confirmed_exit_pnl",
        lambda *_: {"pnl_usd": 2.5, "exit_price": 102.5},
    )
    monkeypatch.setattr(intraday, "_record_daily_pnl", lambda *_: None)
    monkeypatch.setattr(intraday, "_save_state", lambda *_: None)
    monkeypatch.setattr(intraday, "_manage_tracked_positions", lambda *_: set())
    monkeypatch.setattr(intraday, "_load_monthly_managed_symbols", lambda: set())
    monkeypatch.setattr(intraday, "_get_today_pnl", lambda: 0.0)
    monkeypatch.setattr(intraday, "_write_json_atomic", lambda *_: None)
    monkeypatch.setattr(
        intraday,
        "_tg",
        lambda _token, _chat, message: telegram_messages.append(message),
    )

    intraday.run_once(FakeClient(), dry_run=False, strategy_specs={}, csv_paths={})

    assert len(telegram_messages) == 1
    assert "MSFT" in telegram_messages[0]
    assert "📄 PAPER" in telegram_messages[0]
    assert "Realized P&L: $2.50" in telegram_messages[0]


def test_v3_shadow_launcher_is_executable() -> None:
    launcher = ROOT / "scripts" / "run_equities_alpaca_intraday_dynamic_v3_shadow.sh"

    assert launcher.stat().st_mode & stat.S_IXUSR


def test_web_deploy_preserves_instance_auth_config_by_default() -> None:
    script = (ROOT / "scripts" / "deploy_private_web_server.sh").read_text(encoding="utf-8")

    assert 'DEPLOY_WEB_AUTH_CONFIG="${DEPLOY_WEB_AUTH_CONFIG:-0}"' in script
    assert 'if [[ "$DEPLOY_WEB_AUTH_CONFIG" == "1" ]]' in script
    assert "preserving server-owned configs/web_config.json" in script


def test_web_mirror_preserves_source_mtime_and_replaces_atomically() -> None:
    script = (ROOT / "scripts" / "sync_web_live_mirror.sh").read_text(encoding="utf-8")

    assert 'scp -p "${SSH_OPTS[@]}"' in script
    assert 'local local_tmp="${local_path}.sync.$$"' in script
    assert '/bin/mv -f "$local_tmp" "$local_path"' in script
    assert 'write_bundle_manifest "syncing"' in script
    assert 'write_bundle_manifest "complete"' in script
    assert 'write_bundle_manifest "incomplete"' in script
    assert 'CRITICAL_FAILURES' in script


def test_alpaca_live_wrapper_sources_safe_hold_last() -> None:
    wrapper = (ROOT / "scripts" / "run_alpaca_live_v38_once.sh").read_text(encoding="utf-8")
    safe_hold = (ROOT / "configs" / "alpaca_live_v38_safe_hold.env").read_text(encoding="utf-8")

    assert wrapper.index("source configs/alpaca_live_v38_safe_hold.env") > wrapper.index(
        "source configs/alpaca_live_v38.env"
    )
    assert "ALPACA_ALLOW_NEW_ENTRIES=0" in safe_hold
    assert "ALPACA_CLOSE_STALE_POSITIONS=0" in safe_hold
    assert "MONTHLY_MIDMONTH_ROTATION=0" in safe_hold
