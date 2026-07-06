import json

from bot.ai_manual_trade import (
    HARD_RISK_MULT,
    issue_token,
    validate_and_burn_token,
    validate_trade_card,
)


def test_ai_manual_token_is_one_shot(tmp_path):
    token, payload = issue_token(tmp_path, now_ts=1000, ttl_sec=3600)
    assert payload["status"] == "active"
    stored = json.loads((tmp_path / "runtime" / "ai_manual_token.json").read_text())
    assert "token_sha256" in stored
    assert token not in str(stored)

    ok, reason = validate_and_burn_token(token, tmp_path, now_ts=1010)
    assert ok, reason
    ok2, reason2 = validate_and_burn_token(token, tmp_path, now_ts=1020)
    assert not ok2
    assert "token_not_active" in reason2


def test_ai_manual_token_expires(tmp_path):
    token, _payload = issue_token(tmp_path, now_ts=1000, ttl_sec=60)

    ok, reason = validate_and_burn_token(token, tmp_path, now_ts=1061)

    assert not ok
    assert reason == "token_expired"


def test_trade_card_requires_stop_allowlist_and_max_one_position():
    ok, reasons, _norm = validate_trade_card(
        {"symbol": "ILLQUSDT", "side": "Buy", "entry_type": "market", "tp": 1.2},
        open_ai_positions=1,
    )
    assert not ok
    assert "symbol_not_in_liquid_allowlist" in reasons
    assert "sl_required" in reasons
    assert "max_one_ai_manual_position" in reasons


def test_trade_card_normalizes_hard_risk():
    ok, reasons, norm = validate_trade_card(
        {"symbol": "BTCUSDT", "side": "sell", "entry_type": "limit", "sl": "70000", "tp": "65000", "risk_mult": 99}
    )
    assert ok, reasons
    assert norm["side"] == "Sell"
    assert norm["risk_mult"] == HARD_RISK_MULT
