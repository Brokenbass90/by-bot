from __future__ import annotations

import asyncio

import smart_pump_reversal_bot as live


def test_low_sample_ws_window_does_not_become_critical() -> None:
    old_min = live.WS_HEALTH_MIN_CONNECT_DELTA
    try:
        live.WS_HEALTH_MIN_CONNECT_DELTA = 3
        status, disconnect_pct, handshake_pct = live._ws_health_from_delta(2, 3, 2)
    finally:
        live.WS_HEALTH_MIN_CONNECT_DELTA = old_min

    assert status == "LOW_SAMPLE"
    assert disconnect_pct == 150.0
    assert handshake_pct == 100.0


def test_paid_operator_paths_are_default_off() -> None:
    assert live.DEEPSEEK_OPERATOR_USE_API is False
    assert live.DEEPSEEK_OPERATOR_TRADE_REVIEW_ENABLE is False


def test_ws_operator_requires_sample_or_sustained_no_connect(monkeypatch) -> None:
    monkeypatch.setattr(live, "WS_HEALTH_MIN_CONNECT_DELTA", 3)
    monkeypatch.setattr(live, "WS_HEALTH_NO_CONNECT_STREAK_ALERT", 2)
    monkeypatch.setitem(live.WS_TRANSPORT_GUARD, "active", False)
    monkeypatch.setitem(live.WS_TRANSPORT_GUARD, "critical_streak", 1)

    assert live._ws_operator_attention_required("CRITICAL", 2) is False
    assert live._ws_operator_attention_required("CRITICAL", 3) is True
    assert live._ws_operator_attention_required("CRITICAL_NO_CONNECT", 0) is False
    monkeypatch.setitem(live.WS_TRANSPORT_GUARD, "critical_streak", 2)
    assert live._ws_operator_attention_required("CRITICAL_NO_CONNECT", 0) is True


def test_rule_based_fallback_is_not_labeled_as_ai(monkeypatch) -> None:
    sent: list[str] = []

    class FakeOverlay:
        @staticmethod
        def append_shadow_recommendation(**_kwargs):
            return None

    monkeypatch.setattr(live, "DEEPSEEK_OPERATOR_ENABLE", True)
    monkeypatch.setattr(live, "DEEPSEEK_OPERATOR_USE_API", False)
    monkeypatch.setattr(live, "DEEPSEEK_OVERLAY", FakeOverlay())
    monkeypatch.setattr(live, "_ai_operator_duplicate_signature", lambda *_args: "")
    monkeypatch.setattr(live, "_ai_operator_store_memory", lambda **_kwargs: None)
    monkeypatch.setattr(live, "tg_trade", sent.append)

    asyncio.run(
        live._ai_operator_emit(
            kind="proactive_ws_health",
            fallback_text="WS health=CRITICAL",
            payload={},
            prompt="unused",
        )
    )

    assert sent == ["🧭 Rule-based operator\nWS health=CRITICAL"]
