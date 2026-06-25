"""Tests for the russified Telegram + daily digests."""
from scripts.proof_of_life import (
    build_telegram_digest,
    build_daily_digest_ru,
    _regime_ru,
)


def _snap():
    return {
        "generated_at_utc": "2026-06-17T10:00:00Z",
        "heartbeat": {
            "trade_on": True, "regime": "bear_chop", "bybit_msgs": 1200, "open_trades": 1,
            "risk_per_trade_pct": 0.44, "max_positions": 3, "allocator_hard_block": False,
            "allocator_safe_mode": False, "max_open_portfolio_risk_pct": 6.0,
            "strategy_runtime_config": {
                "enabled": {"range": True, "flat": True, "ivb1": True},
                "risk_mult": {"range": 0.25, "flat": 0.30, "ivb1": 0.0},
            },
        },
        "pnl_by_sleeve": {
            "alt_range_scalp_v1": {"pnl": 1.23, "n": 8},
            "flat_resistance_fade": {"pnl": -0.5, "n": 3},
        },
        "recent_trade_events": [
            {"event": "close", "strategy": "alt_range_scalp_v1", "symbol": "SOLUSDT", "ts": 1718600000}
        ],
    }


def test_regime_translation():
    assert _regime_ru("bear_chop") == "медвежий флэт"
    assert _regime_ru("bull_trend") == "бычий тренд"


def test_telegram_digest_is_russian_and_human():
    txt = build_telegram_digest(_snap())
    assert "ПУЛЬС БОТА" in txt
    assert "ЖИВ И ТОРГУЕТ" in txt
    assert "медвежий флэт" in txt
    assert "В БОЮ" in txt and "пила во флэте" in txt
    assert "BOT PULSE" not in txt  # no leftover English


def test_daily_digest_adds_pnl_and_risk_sections():
    txt = build_daily_digest_ru(_snap())
    assert "ПУЛЬС БОТА" in txt           # includes the pulse header
    assert "P&L по рукавам" in txt
    assert "пила во флэте" in txt        # live sleeve P&L line, human name
    assert "Риск-постура" in txt
    assert "лимит портфельного риска: 6.0%" in txt
    assert "открыто позиций: 1" in txt
